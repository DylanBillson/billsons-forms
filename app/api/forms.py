import json

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.orm import Session

from app.db.models.endpoint_delivery_log import EndpointDeliveryLog
from app.db.models.form_endpoint import FormEndpoint
from app.db.models.form_endpoint_recipient import FormEndpointRecipient
from app.db.session import get_db
from app.services.cap import verify_cap_token
from app.services.email import build_submission_email_body, send_submission_email
from app.core.encryption import decrypt_value

router = APIRouter(prefix="/api/v1/forms")


def response_for_endpoint(
    endpoint: FormEndpoint,
    success: bool,
    message: str,
    status_code: int,
) -> Response:
    if success and endpoint.success_redirect_url:
        return RedirectResponse(endpoint.success_redirect_url, status_code=303)

    if not success and endpoint.error_redirect_url:
        return RedirectResponse(endpoint.error_redirect_url, status_code=303)

    return JSONResponse(
        {"success": success, "message": message},
        status_code=status_code,
    )


def get_allowed_origins(endpoint: FormEndpoint) -> list[str]:
    if not endpoint.allowed_origins:
        return []

    try:
        parsed = json.loads(endpoint.allowed_origins)
    except json.JSONDecodeError:
        return []

    if not isinstance(parsed, list):
        return []

    return [str(origin).strip() for origin in parsed if str(origin).strip()]


async def parse_payload(request: Request) -> dict[str, object]:
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        data = await request.json()
        if isinstance(data, dict):
            return data
        return {}

    form = await request.form()
    return dict(form)


def payload_size_bytes(payload: dict[str, object]) -> int:
    return len(json.dumps(payload, default=str).encode("utf-8"))


def get_reply_to_email(
    endpoint: FormEndpoint,
    payload: dict[str, object],
) -> str | None:
    if not endpoint.reply_to_field:
        return None

    value = payload.get(endpoint.reply_to_field)

    if not value:
        return None

    return str(value).strip() or None


def get_cap_token(payload: dict[str, object]) -> str | None:
    for key in ("cap-token", "cap_token", "cap_response", "cf-turnstile-response", "g-recaptcha-response"):
        value = payload.get(key)
        if value:
            return str(value)

    return None


def create_delivery_log(
    db: Session,
    *,
    endpoint: FormEndpoint,
    request: Request,
    success: bool,
    cap_verified: bool,
    payload_size: int | None,
    recipient_summary: str | None = None,
    error_message: str | None = None,
) -> None:
    log = EndpointDeliveryLog(
        endpoint_id=endpoint.id,
        success=success,
        ip_address=request.client.host if request.client else None,
        origin=request.headers.get("origin"),
        user_agent=request.headers.get("user-agent"),
        cap_verified=cap_verified,
        smtp_host=endpoint.smtp_host,
        smtp_port=endpoint.smtp_port,
        sender_email=endpoint.sender_email,
        recipient_summary=recipient_summary,
        payload_size_bytes=payload_size,
        error_message=error_message,
    )

    db.add(log)
    db.commit()


@router.post("/{slug}")
async def submit_form(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    endpoint = (
        db.query(FormEndpoint)
        .filter(FormEndpoint.slug == slug)
        .filter(FormEndpoint.is_deleted.is_(False))
        .first()
    )

    if not endpoint:
        return JSONResponse(
            {"success": False, "message": "Endpoint not found."},
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if not endpoint.is_active:
        return response_for_endpoint(
            endpoint,
            success=False,
            message="Endpoint is disabled.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    payload = await parse_payload(request)
    size_bytes = payload_size_bytes(payload)

    max_bytes = endpoint.max_payload_kb * 1024
    if size_bytes > max_bytes:
        create_delivery_log(
            db,
            endpoint=endpoint,
            request=request,
            success=False,
            cap_verified=False,
            payload_size=size_bytes,
            error_message="Payload too large.",
        )

        return response_for_endpoint(
            endpoint,
            success=False,
            message="Payload too large.",
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        )

    allowed_origins = get_allowed_origins(endpoint)
    request_origin = request.headers.get("origin")

    if allowed_origins and request_origin and request_origin not in allowed_origins:
        create_delivery_log(
            db,
            endpoint=endpoint,
            request=request,
            success=False,
            cap_verified=False,
            payload_size=size_bytes,
            error_message="Origin not allowed.",
        )

        return response_for_endpoint(
            endpoint,
            success=False,
            message="Origin not allowed.",
            status_code=status.HTTP_403_FORBIDDEN,
        )

    cap_verified = False

    if endpoint.cap_enabled:
        cap_token = get_cap_token(payload)

        cap_verified = await verify_cap_token(
            verify_url=endpoint.cap_verify_url or "",
            secret_key=decrypt_value(endpoint.cap_secret_key) or "",
            token=cap_token or "",
        )

        if not cap_verified:
            create_delivery_log(
                db,
                endpoint=endpoint,
                request=request,
                success=False,
                cap_verified=False,
                payload_size=size_bytes,
                error_message="CAP verification failed.",
            )

            return response_for_endpoint(
                endpoint,
                success=False,
                message="CAP verification failed.",
                status_code=status.HTTP_403_FORBIDDEN,
            )

    recipients = (
        db.query(FormEndpointRecipient)
        .filter(FormEndpointRecipient.endpoint_id == endpoint.id)
        .filter(FormEndpointRecipient.is_active.is_(True))
        .all()
    )

    recipient_emails = [recipient.email for recipient in recipients]

    if not recipient_emails:
        create_delivery_log(
            db,
            endpoint=endpoint,
            request=request,
            success=False,
            cap_verified=cap_verified,
            payload_size=size_bytes,
            error_message="No active recipients configured.",
        )

        return response_for_endpoint(
            endpoint,
            success=False,
            message="No active recipients configured.",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    reply_to_email = get_reply_to_email(endpoint, payload)
    body = build_submission_email_body(payload)

    try:
        send_submission_email(
            smtp_host=endpoint.smtp_host,
            smtp_port=endpoint.smtp_port,
            smtp_username=endpoint.smtp_username,
            smtp_password=decrypt_value(endpoint.smtp_password),
            smtp_security=endpoint.smtp_security,
            sender_email=endpoint.sender_email,
            sender_name=endpoint.sender_name,
            recipients=recipient_emails,
            subject=endpoint.email_subject,
            body=body,
            reply_to_email=reply_to_email,
        )
    except Exception as exc:
        create_delivery_log(
            db,
            endpoint=endpoint,
            request=request,
            success=False,
            cap_verified=cap_verified,
            payload_size=size_bytes,
            recipient_summary=", ".join(recipient_emails),
            error_message=str(exc),
        )

        return response_for_endpoint(
            endpoint,
            success=False,
            message="Email delivery failed.",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    create_delivery_log(
        db,
        endpoint=endpoint,
        request=request,
        success=True,
        cap_verified=cap_verified,
        payload_size=size_bytes,
        recipient_summary=", ".join(recipient_emails),
    )

    return response_for_endpoint(
        endpoint,
        success=True,
        message="Form submitted successfully.",
        status_code=status.HTTP_200_OK,
    )