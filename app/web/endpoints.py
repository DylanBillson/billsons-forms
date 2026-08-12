from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.csrf import require_csrf
from app.core.config import settings
from app.core.encryption import decrypt_value, encrypt_value
from app.core.endpoint_validation import validate_endpoint_config
from app.core.origins import origins_from_storage, origins_to_storage
from app.db.models.email_delivery_job import EmailDeliveryJob
from app.db.models.endpoint_delivery_log import EndpointDeliveryLog
from app.db.models.form_endpoint import FormEndpoint
from app.db.models.form_endpoint_recipient import FormEndpointRecipient
from app.db.models.user import User
from app.db.session import get_db
from app.services.audit import create_audit_log
from app.services.cap import CAPStatus, test_cap_service
from app.services.email import send_test_email
from app.web.dashboard import require_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_endpoint(db: Session, endpoint_id: int) -> FormEndpoint | None:
    return db.query(FormEndpoint).filter(FormEndpoint.id == endpoint_id, FormEndpoint.is_deleted.is_(False)).first()


def endpoint_form(endpoint: FormEndpoint, recipients: list[FormEndpointRecipient]) -> dict[str, object]:
    return {
        "name": endpoint.name, "slug": endpoint.slug, "description": endpoint.description or "",
        "recipients": "\n".join(item.email for item in recipients), "sender_email": endpoint.sender_email,
        "sender_name": endpoint.sender_name or "", "smtp_host": endpoint.smtp_host, "smtp_port": endpoint.smtp_port,
        "smtp_username": endpoint.smtp_username or "", "smtp_security": endpoint.smtp_security,
        "reply_to_field": endpoint.reply_to_field or "", "cap_enabled": endpoint.cap_enabled,
        "cap_verify_url": endpoint.cap_verify_url or "", "cap_site_key": endpoint.cap_site_key or "",
        "success_redirect_url": endpoint.success_redirect_url or "", "error_redirect_url": endpoint.error_redirect_url or "",
        "allowed_origins": "\n".join(origins_from_storage(endpoint.allowed_origins)), "max_payload_kb": endpoint.max_payload_kb,
        "rate_limit_enabled": endpoint.rate_limit_enabled, "rate_limit_requests": endpoint.rate_limit_requests,
        "rate_limit_window_seconds": endpoint.rate_limit_window_seconds, "is_active": endpoint.is_active,
    }


async def submitted_form(request: Request) -> dict[str, object]:
    form = await request.form()
    keys = (
        "name", "slug", "description", "recipients", "sender_email", "sender_name", "smtp_host", "smtp_port",
        "smtp_username", "smtp_password", "smtp_security", "reply_to_field", "cap_verify_url", "cap_site_key",
        "cap_secret_key", "success_redirect_url", "error_redirect_url", "allowed_origins", "max_payload_kb",
        "rate_limit_requests", "rate_limit_window_seconds",
    )
    data: dict[str, object] = {key: str(form.get(key, "")) for key in keys}
    for key in ("cap_enabled", "rate_limit_enabled", "is_active"):
        data[key] = key in form
    return data


def render_form(template: str, request: Request, current_user: User, form: dict[str, object], errors: dict[str, str], endpoint: FormEndpoint | None = None):
    return templates.TemplateResponse(
        template,
        {"request": request, "current_user": current_user, "endpoint": endpoint, "form": form, "errors": errors, "error": next(iter(errors.values()), None)},
        status_code=status.HTTP_400_BAD_REQUEST,
    )


def apply_values(endpoint: FormEndpoint, values: dict[str, object], raw: dict[str, object]) -> None:
    endpoint.name = str(values["name"])
    endpoint.slug = str(values["slug"])
    endpoint.description = str(raw.get("description", "")).strip() or None
    endpoint.is_active = bool(raw.get("is_active"))
    endpoint.success_redirect_url = values["success_redirect_url"] or None
    endpoint.error_redirect_url = values["error_redirect_url"] or None
    endpoint.allowed_origins = origins_to_storage(values["normalized_origins"])
    endpoint.reply_to_field = str(values["reply_to_field"]) or None
    endpoint.smtp_host = str(values["smtp_host"])
    endpoint.smtp_port = int(values["smtp_port"])
    endpoint.smtp_username = str(values["smtp_username"]) or None
    endpoint.smtp_security = str(values["smtp_security"])
    endpoint.sender_email = str(values["sender_email"])
    endpoint.sender_name = str(raw.get("sender_name", "")).strip() or None
    endpoint.cap_enabled = bool(raw.get("cap_enabled"))
    endpoint.cap_verify_url = values["cap_verify_url"] or None
    endpoint.cap_site_key = str(values["cap_site_key"]) or None
    endpoint.max_payload_kb = int(values["max_payload_kb"])
    endpoint.rate_limit_enabled = bool(raw.get("rate_limit_enabled"))
    endpoint.rate_limit_requests = int(values["rate_limit_requests"])
    endpoint.rate_limit_window_seconds = int(values["rate_limit_window_seconds"])
    if str(raw.get("smtp_password", "")).strip():
        endpoint.smtp_password = encrypt_value(str(raw["smtp_password"]).strip())
    if str(raw.get("cap_secret_key", "")).strip():
        endpoint.cap_secret_key = encrypt_value(str(raw["cap_secret_key"]).strip())


def replace_recipients(db: Session, endpoint: FormEndpoint, emails: list[str]) -> None:
    db.query(FormEndpointRecipient).filter_by(endpoint_id=endpoint.id).delete(synchronize_session=False)
    for email in emails:
        db.add(FormEndpointRecipient(endpoint_id=endpoint.id, email=email, recipient_type="to", is_active=True))


@router.get("/endpoints")
async def endpoint_index(request: Request, db: Session = Depends(get_db), current_user=Depends(require_user)):
    if isinstance(current_user, RedirectResponse): return current_user
    endpoints = db.query(FormEndpoint).filter(FormEndpoint.is_deleted.is_(False)).order_by(FormEndpoint.name).all()
    return templates.TemplateResponse("endpoints/index.html", {"request": request, "current_user": current_user, "endpoints": endpoints})


@router.get("/endpoints/new")
async def endpoint_create_page(request: Request, current_user=Depends(require_user)):
    if isinstance(current_user, RedirectResponse): return current_user
    defaults = {
        "max_payload_kb": min(256, settings.absolute_max_payload_kb), "rate_limit_enabled": True,
        "rate_limit_requests": settings.default_form_rate_limit_requests,
        "rate_limit_window_seconds": settings.default_form_rate_limit_window_seconds, "is_active": True,
    }
    return templates.TemplateResponse("endpoints/create.html", {"request": request, "current_user": current_user, "form": defaults, "errors": {}, "error": None})


@router.post("/endpoints/new", dependencies=[Depends(require_csrf)])
async def endpoint_create_submit(request: Request, db: Session = Depends(get_db), current_user=Depends(require_user)):
    if isinstance(current_user, RedirectResponse): return current_user
    raw = await submitted_form(request)
    result = validate_endpoint_config(raw)
    if db.query(FormEndpoint).filter_by(slug=result.values["slug"]).first():
        result.errors["slug"] = "An endpoint already uses this slug."
    if not result.is_valid:
        return render_form("endpoints/create.html", request, current_user, raw, result.errors)
    endpoint = FormEndpoint(owner_user_id=current_user.id, is_deleted=False, email_subject="New form submission", email_template=None)
    apply_values(endpoint, result.values, raw)
    db.add(endpoint); db.flush()
    replace_recipients(db, endpoint, result.values["recipient_emails"])
    create_audit_log(db, action="Endpoint Created", user=current_user, request=request, details=f"Created endpoint: {endpoint.name} ({endpoint.slug})")
    db.commit()
    return RedirectResponse(f"/endpoints/{endpoint.id}", status_code=303)


@router.get("/endpoints/{endpoint_id}")
async def endpoint_view_page(endpoint_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_user)):
    if isinstance(current_user, RedirectResponse): return current_user
    endpoint = get_endpoint(db, endpoint_id)
    if not endpoint: return RedirectResponse("/endpoints", status_code=303)
    recipients = db.query(FormEndpointRecipient).filter_by(endpoint_id=endpoint.id, is_active=True).order_by(FormEndpointRecipient.email).all()
    logs = db.query(EndpointDeliveryLog).filter_by(endpoint_id=endpoint.id).order_by(EndpointDeliveryLog.created_at.desc()).limit(20).all()
    jobs = db.query(EmailDeliveryJob).filter_by(endpoint_id=endpoint.id).order_by(EmailDeliveryJob.created_at.desc()).limit(20).all()
    return templates.TemplateResponse("endpoints/view.html", {
        "request": request, "current_user": current_user, "endpoint": endpoint, "recipients": recipients,
        "allowed_origins": origins_from_storage(endpoint.allowed_origins), "delivery_logs": logs, "delivery_jobs": jobs,
        "notice": request.query_params.get("notice"), "test_error": request.query_params.get("error"),
    })


@router.get("/endpoints/{endpoint_id}/edit")
async def endpoint_edit_page(endpoint_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_user)):
    if isinstance(current_user, RedirectResponse): return current_user
    endpoint = get_endpoint(db, endpoint_id)
    if not endpoint: return RedirectResponse("/endpoints", status_code=303)
    recipients = db.query(FormEndpointRecipient).filter_by(endpoint_id=endpoint.id, is_active=True).order_by(FormEndpointRecipient.email).all()
    return templates.TemplateResponse("endpoints/edit.html", {"request": request, "current_user": current_user, "endpoint": endpoint, "form": endpoint_form(endpoint, recipients), "errors": {}, "error": None})


@router.post("/endpoints/{endpoint_id}/edit", dependencies=[Depends(require_csrf)])
async def endpoint_edit_submit(endpoint_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_user)):
    if isinstance(current_user, RedirectResponse): return current_user
    endpoint = get_endpoint(db, endpoint_id)
    if not endpoint: return RedirectResponse("/endpoints", status_code=303)
    raw = await submitted_form(request)
    result = validate_endpoint_config(raw, existing_smtp_secret=bool(endpoint.smtp_password), existing_cap_secret=bool(endpoint.cap_secret_key))
    duplicate = db.query(FormEndpoint).filter(FormEndpoint.slug == result.values["slug"], FormEndpoint.id != endpoint.id).first()
    if duplicate: result.errors["slug"] = "Another endpoint already uses this slug."
    if not result.is_valid: return render_form("endpoints/edit.html", request, current_user, raw, result.errors, endpoint)
    old = f"{endpoint.name} ({endpoint.slug})"
    apply_values(endpoint, result.values, raw)
    replace_recipients(db, endpoint, result.values["recipient_emails"])
    create_audit_log(db, action="Endpoint Updated", user=current_user, request=request, details=f"Updated endpoint: {old} -> {endpoint.name} ({endpoint.slug})")
    db.commit()
    return RedirectResponse(f"/endpoints/{endpoint.id}", status_code=303)


@router.post("/endpoints/{endpoint_id}/delete", dependencies=[Depends(require_csrf)])
async def endpoint_delete_submit(endpoint_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_user)):
    if isinstance(current_user, RedirectResponse): return current_user
    endpoint = get_endpoint(db, endpoint_id)
    if endpoint:
        endpoint.is_deleted = True; endpoint.is_active = False
        create_audit_log(db, action="Endpoint Deleted", user=current_user, request=request, details=f"Soft deleted endpoint: {endpoint.name} ({endpoint.slug})")
        db.commit()
    return RedirectResponse("/endpoints", status_code=303)


@router.post("/endpoints/{endpoint_id}/test-smtp", dependencies=[Depends(require_csrf)])
async def test_smtp(endpoint_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_user)):
    if isinstance(current_user, RedirectResponse): return current_user
    endpoint = get_endpoint(db, endpoint_id)
    if not endpoint: return RedirectResponse("/endpoints", status_code=303)
    recipients = [item.email for item in db.query(FormEndpointRecipient).filter_by(endpoint_id=endpoint.id, is_active=True).all()]
    try:
        await send_test_email(
            smtp_host=endpoint.smtp_host, smtp_port=endpoint.smtp_port, smtp_username=endpoint.smtp_username,
            smtp_password=decrypt_value(endpoint.smtp_password), smtp_security=endpoint.smtp_security,
            sender_email=endpoint.sender_email, sender_name=endpoint.sender_name, recipients=recipients,
            reply_to_email=None,
        )
        message, query = "SMTP configuration test succeeded.", "notice=SMTP+configuration+test+succeeded."
    except Exception as exc:
        message, query = f"SMTP test failed: {type(exc).__name__}", f"error=SMTP+test+failed%3A+{type(exc).__name__}"
    create_audit_log(db, action="SMTP Configuration Tested", user=current_user, request=request, details=f"Endpoint {endpoint.slug}: {message}")
    db.commit()
    return RedirectResponse(f"/endpoints/{endpoint.id}?{query}", status_code=303)


@router.post("/endpoints/{endpoint_id}/test-cap", dependencies=[Depends(require_csrf)])
async def test_cap(endpoint_id: int, request: Request, db: Session = Depends(get_db), current_user=Depends(require_user)):
    if isinstance(current_user, RedirectResponse): return current_user
    endpoint = get_endpoint(db, endpoint_id)
    if not endpoint: return RedirectResponse("/endpoints", status_code=303)
    result = await test_cap_service(endpoint.cap_verify_url or "")
    ok = result.status is CAPStatus.SUCCESS
    create_audit_log(db, action="CAP Configuration Tested", user=current_user, request=request, details=f"Endpoint {endpoint.slug}: {result.status.value}; {result.diagnostic}")
    db.commit()
    key = "notice" if ok else "error"
    from urllib.parse import quote_plus
    return RedirectResponse(f"/endpoints/{endpoint.id}?{key}={quote_plus(result.diagnostic)}", status_code=303)
