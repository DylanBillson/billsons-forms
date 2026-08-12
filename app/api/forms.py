from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.core.client_ip import get_client_ip
from app.core.config import settings
from app.core.cors import apply_cors, preflight_response
from app.core.encryption import decrypt_value
from app.core.origins import origin_is_allowed, origins_from_storage
from app.db.models.endpoint_delivery_log import EndpointDeliveryLog
from app.db.models.form_endpoint import FormEndpoint
from app.db.models.form_endpoint_recipient import FormEndpointRecipient
from app.db.session import get_db
from app.services.cap import CAPStatus, verify_cap_token
from app.services.delivery_queue import DeliverySnapshot, create_delivery_snapshot, enqueue_delivery
from app.services.payloads import parse_submission_payload
from app.services.rate_limit import check_rate_limit
from app.core.endpoint_validation import is_email

router = APIRouter(prefix="/api/v1/forms")


def get_endpoint(db: Session, slug: str) -> FormEndpoint | None:
    return db.query(FormEndpoint).filter(FormEndpoint.slug == slug, FormEndpoint.is_deleted.is_(False)).first()


def endpoint_response(endpoint: FormEndpoint, *, success: bool, message: str, status_code: int, origin: str | None, allowed_origins: list[str], headers: dict[str, str] | None = None) -> Response:
    if success and endpoint.success_redirect_url:
        response: Response = RedirectResponse(endpoint.success_redirect_url, status_code=303)
    elif not success and endpoint.error_redirect_url and status_code < 500:
        response = RedirectResponse(endpoint.error_redirect_url, status_code=303)
    else:
        response = JSONResponse({"success": success, "message": message}, status_code=status_code)
    for key, value in (headers or {}).items():
        response.headers[key] = value
    return apply_cors(response, origin, allowed_origins)


def delivery_log(db: Session, endpoint: FormEndpoint, request: Request, *, success: bool = False, cap_verified: bool = False, payload_size: int | None = None, error: str | None = None, job_id: int | None = None, delivery_status: str | None = None, recipient_summary: str | None = None, snapshot: DeliverySnapshot | None = None) -> EndpointDeliveryLog:
    log = EndpointDeliveryLog(
        endpoint_id=endpoint.id, success=success, ip_address=get_client_ip(request),
        origin=request.headers.get("origin"), user_agent=request.headers.get("user-agent"),
        cap_verified=cap_verified, smtp_host=snapshot.smtp_host if snapshot else endpoint.smtp_host,
        smtp_port=snapshot.smtp_port if snapshot else endpoint.smtp_port,
        sender_email=snapshot.sender_email if snapshot else endpoint.sender_email,
        recipient_summary=recipient_summary,
        payload_size_bytes=payload_size, error_message=error, delivery_job_id=job_id,
        delivery_status=delivery_status,
    )
    db.add(log)
    return log


@router.options("/{slug}")
async def form_preflight(slug: str, request: Request, db: Session = Depends(get_db)):
    endpoint = get_endpoint(db, slug)
    if not endpoint or not endpoint.is_active:
        return Response(status_code=404)
    allowed_origins = origins_from_storage(endpoint.allowed_origins)
    origin = request.headers.get("origin")
    return preflight_response(request, allowed_origins, bool(origin) and origin_is_allowed(origin, allowed_origins))


@router.post("/{slug}")
async def submit_form(slug: str, request: Request, db: Session = Depends(get_db)):
    endpoint = get_endpoint(db, slug)
    if not endpoint:
        return JSONResponse({"success": False, "message": "Endpoint not found."}, status_code=404)
    allowed_origins = origins_from_storage(endpoint.allowed_origins)
    origin = request.headers.get("origin")
    if not endpoint.is_active:
        return endpoint_response(endpoint, success=False, message="Endpoint is disabled.", status_code=403, origin=origin, allowed_origins=allowed_origins)

    # Origin and rate checks deliberately happen before any request body is parsed.
    if not origin_is_allowed(origin, allowed_origins):
        delivery_log(db, endpoint, request, error="Origin missing, malformed or not allowed.")
        db.commit()
        return endpoint_response(endpoint, success=False, message="Origin not allowed.", status_code=403, origin=origin, allowed_origins=allowed_origins)

    client_ip = get_client_ip(request) or "unknown"
    if endpoint.rate_limit_enabled:
        decision = check_rate_limit(
            db, scope=f"form:{endpoint.id}", identity=client_ip,
            limit=endpoint.rate_limit_requests, window_seconds=endpoint.rate_limit_window_seconds,
        )
        if not decision.allowed:
            delivery_log(db, endpoint, request, error="Submission rate limit exceeded.")
            db.commit()
            return endpoint_response(
                endpoint, success=False, message="Too many submissions. Try again later.", status_code=429,
                origin=origin, allowed_origins=allowed_origins,
                headers={"Retry-After": str(decision.retry_after), "X-RateLimit-Limit": str(decision.limit), "X-RateLimit-Remaining": "0"},
            )

    max_bytes = min(endpoint.max_payload_kb, settings.absolute_max_payload_kb) * 1024
    try:
        payload, size_bytes = await parse_submission_payload(request, max_bytes)
    except HTTPException as exc:
        delivery_log(db, endpoint, request, error=str(exc.detail))
        db.commit()
        return endpoint_response(endpoint, success=False, message=str(exc.detail), status_code=exc.status_code, origin=origin, allowed_origins=allowed_origins)

    cap_verified = False
    if endpoint.cap_enabled:
        token = next((str(payload[key]) for key in ("cap-token", "cap_token", "cap_response", "cf-turnstile-response", "g-recaptcha-response") if payload.get(key)), "")
        cap_result = await verify_cap_token(endpoint.cap_verify_url or "", decrypt_value(endpoint.cap_secret_key) or "", token)
        cap_verified = cap_result.verified
        if not cap_verified:
            delivery_log(db, endpoint, request, payload_size=size_bytes, error=f"CAP {cap_result.status.value}: {cap_result.diagnostic}")
            db.commit()
            public_status = 403 if cap_result.status is CAPStatus.REJECTED else 503
            public_message = "CAP verification failed." if public_status == 403 else "CAP verification is temporarily unavailable."
            return endpoint_response(endpoint, success=False, message=public_message, status_code=public_status, origin=origin, allowed_origins=allowed_origins)

    recipients = db.query(FormEndpointRecipient).filter_by(endpoint_id=endpoint.id, is_active=True).all()
    if not recipients:
        delivery_log(db, endpoint, request, cap_verified=cap_verified, payload_size=size_bytes, error="No active recipients configured.")
        db.commit()
        return endpoint_response(endpoint, success=False, message="Endpoint is not configured for delivery.", status_code=503, origin=origin, allowed_origins=allowed_origins)

    reply_to_email: str | None = None
    if endpoint.reply_to_field and payload.get(endpoint.reply_to_field):
        reply_to = payload[endpoint.reply_to_field]
        if not isinstance(reply_to, str) or not is_email(reply_to.strip()):
            delivery_log(db, endpoint, request, cap_verified=cap_verified, payload_size=size_bytes, error="Reply-To field did not contain a valid email address.")
            db.commit()
            return endpoint_response(endpoint, success=False, message="The reply email field is invalid.", status_code=400, origin=origin, allowed_origins=allowed_origins)
        reply_to_email = reply_to.strip()

    try:
        snapshot = create_delivery_snapshot(
            submitted_fields=payload,
            recipients=[item.email for item in recipients],
            sender_email=endpoint.sender_email,
            sender_name=endpoint.sender_name,
            subject=endpoint.email_subject,
            smtp_host=endpoint.smtp_host,
            smtp_port=endpoint.smtp_port,
            smtp_username=endpoint.smtp_username,
            smtp_password=decrypt_value(endpoint.smtp_password),
            smtp_security=endpoint.smtp_security,
            reply_to_email=reply_to_email,
        )
        job = enqueue_delivery(db, endpoint_id=endpoint.id, snapshot=snapshot)
        delivery_log(
            db, endpoint, request, success=True, cap_verified=cap_verified, payload_size=size_bytes,
            job_id=job.id, delivery_status="queued", recipient_summary=", ".join(snapshot.recipients), snapshot=snapshot,
        )
        db.commit()
    except Exception:
        db.rollback()
        return endpoint_response(endpoint, success=False, message="Submission could not be queued.", status_code=503, origin=origin, allowed_origins=allowed_origins)

    return endpoint_response(endpoint, success=True, message="Form submission accepted for delivery.", status_code=status.HTTP_202_ACCEPTED, origin=origin, allowed_origins=allowed_origins)
