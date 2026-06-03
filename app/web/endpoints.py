import json
import re

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.encryption import encrypt_value
from app.db.models.endpoint_delivery_log import EndpointDeliveryLog
from app.db.models.form_endpoint import FormEndpoint
from app.db.models.form_endpoint_recipient import FormEndpointRecipient
from app.db.models.user import User
from app.db.session import get_db
from app.services.audit import create_audit_log
from app.web.dashboard import require_user

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def parse_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


def normalise_origins(value: str) -> str | None:
    origins = parse_lines(value)
    if not origins:
        return None
    return json.dumps(origins)


def denormalise_origins(value: str | None) -> str:
    if not value:
        return ""

    try:
        origins = json.loads(value)
    except json.JSONDecodeError:
        return ""

    if not isinstance(origins, list):
        return ""

    return "\n".join(str(origin) for origin in origins)


def parse_origins_for_view(value: str | None) -> list[str]:
    if not value:
        return []

    try:
        origins = json.loads(value)
    except json.JSONDecodeError:
        return []

    if not isinstance(origins, list):
        return []

    return [str(origin) for origin in origins]


def get_endpoint_for_user(
    db: Session,
    endpoint_id: int,
    current_user: User,
) -> FormEndpoint | None:
    query = (
        db.query(FormEndpoint)
        .filter(FormEndpoint.id == endpoint_id)
        .filter(FormEndpoint.is_deleted.is_(False))
    )

    return query.first()


@router.get("/endpoints")
async def endpoint_index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | RedirectResponse = Depends(require_user),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    query = db.query(FormEndpoint).filter(FormEndpoint.is_deleted.is_(False))

    endpoints = query.order_by(FormEndpoint.name.asc()).all()

    return templates.TemplateResponse(
        "endpoints/index.html",
        {
            "request": request,
            "current_user": current_user,
            "endpoints": endpoints,
        },
    )


@router.get("/endpoints/new")
async def endpoint_create_page(
    request: Request,
    current_user: User | RedirectResponse = Depends(require_user),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    return templates.TemplateResponse(
        "endpoints/create.html",
        {
            "request": request,
            "current_user": current_user,
            "error": None,
            "form": {},
        },
    )


@router.post("/endpoints/new")
async def endpoint_create_submit(
    request: Request,
    name: str = Form(...),
    slug: str = Form(...),
    description: str = Form(""),
    recipients: str = Form(...),
    sender_email: str = Form(...),
    sender_name: str = Form(""),
    smtp_host: str = Form(...),
    smtp_port: int = Form(587),
    smtp_username: str = Form(""),
    smtp_password: str = Form(""),
    smtp_security: str = Form("starttls"),
    reply_to_field: str = Form("email"),
    cap_enabled: bool = Form(False),
    cap_verify_url: str = Form(""),
    cap_site_key: str = Form(""),
    cap_secret_key: str = Form(""),
    success_redirect_url: str = Form(""),
    error_redirect_url: str = Form(""),
    allowed_origins: str = Form(""),
    max_payload_kb: int = Form(256),
    is_active: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User | RedirectResponse = Depends(require_user),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    slug = slug.strip().lower()
    recipient_emails = parse_lines(recipients)

    form_data = {
        "name": name,
        "slug": slug,
        "description": description,
        "recipients": recipients,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_username": smtp_username,
        "smtp_security": smtp_security,
        "reply_to_field": reply_to_field,
        "cap_enabled": cap_enabled,
        "cap_verify_url": cap_verify_url,
        "cap_site_key": cap_site_key,
        "success_redirect_url": success_redirect_url,
        "error_redirect_url": error_redirect_url,
        "allowed_origins": allowed_origins,
        "max_payload_kb": max_payload_kb,
        "is_active": is_active,
    }

    if not SLUG_PATTERN.match(slug):
        return templates.TemplateResponse(
            "endpoints/create.html",
            {
                "request": request,
                "current_user": current_user,
                "error": "Slug must use lowercase letters, numbers and hyphens only.",
                "form": form_data,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not recipient_emails:
        return templates.TemplateResponse(
            "endpoints/create.html",
            {
                "request": request,
                "current_user": current_user,
                "error": "At least one recipient email is required.",
                "form": form_data,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    existing_endpoint = db.query(FormEndpoint).filter(FormEndpoint.slug == slug).first()

    if existing_endpoint:
        return templates.TemplateResponse(
            "endpoints/create.html",
            {
                "request": request,
                "current_user": current_user,
                "error": "An endpoint with that slug already exists.",
                "form": form_data,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    endpoint = FormEndpoint(
        name=name.strip(),
        slug=slug,
        description=description.strip() or None,
        owner_user_id=current_user.id,
        is_active=is_active,
        is_deleted=False,
        success_redirect_url=success_redirect_url.strip() or None,
        error_redirect_url=error_redirect_url.strip() or None,
        allowed_origins=normalise_origins(allowed_origins),
        reply_to_field=reply_to_field.strip() or None,
        email_subject="New form submission",
        email_template=None,
        smtp_host=smtp_host.strip(),
        smtp_port=smtp_port,
        smtp_username=smtp_username.strip() or None,
        smtp_password=encrypt_value(smtp_password.strip() or None),
        smtp_security=smtp_security,
        sender_email=sender_email.strip(),
        sender_name=sender_name.strip() or None,
        cap_enabled=cap_enabled,
        cap_verify_url=cap_verify_url.strip() or None,
        cap_site_key=cap_site_key.strip() or None,
        cap_secret_key=encrypt_value(cap_secret_key.strip() or None),
        max_payload_kb=max_payload_kb,
    )

    db.add(endpoint)
    db.flush()

    for email in recipient_emails:
        db.add(
            FormEndpointRecipient(
                endpoint_id=endpoint.id,
                email=email,
                recipient_type="to",
                is_active=True,
            )
        )

    create_audit_log(
        db,
        action="Endpoint Created",
        user=current_user,
        request=request,
        details=f"Created endpoint: {endpoint.name} ({endpoint.slug})",
    )

    db.commit()

    return RedirectResponse(
        url=f"/endpoints/{endpoint.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/endpoints/{endpoint_id}")
async def endpoint_view_page(
    endpoint_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | RedirectResponse = Depends(require_user),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    endpoint = get_endpoint_for_user(db, endpoint_id, current_user)

    if not endpoint:
        return RedirectResponse(
            url="/endpoints",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    recipients = (
        db.query(FormEndpointRecipient)
        .filter(FormEndpointRecipient.endpoint_id == endpoint.id)
        .filter(FormEndpointRecipient.is_active.is_(True))
        .order_by(FormEndpointRecipient.email.asc())
        .all()
    )

    delivery_logs = (
        db.query(EndpointDeliveryLog)
        .filter(EndpointDeliveryLog.endpoint_id == endpoint.id)
        .order_by(EndpointDeliveryLog.created_at.desc())
        .limit(20)
        .all()
    )

    return templates.TemplateResponse(
        "endpoints/view.html",
        {
            "request": request,
            "current_user": current_user,
            "endpoint": endpoint,
            "recipients": recipients,
            "allowed_origins": parse_origins_for_view(endpoint.allowed_origins),
            "delivery_logs": delivery_logs,
        },
    )


@router.get("/endpoints/{endpoint_id}/edit")
async def endpoint_edit_page(
    endpoint_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | RedirectResponse = Depends(require_user),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    endpoint = get_endpoint_for_user(db, endpoint_id, current_user)

    if not endpoint:
        return RedirectResponse(
            url="/endpoints",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    recipients = (
        db.query(FormEndpointRecipient)
        .filter(FormEndpointRecipient.endpoint_id == endpoint.id)
        .filter(FormEndpointRecipient.is_active.is_(True))
        .order_by(FormEndpointRecipient.email.asc())
        .all()
    )

    form = {
        "name": endpoint.name,
        "slug": endpoint.slug,
        "description": endpoint.description or "",
        "recipients": "\n".join(recipient.email for recipient in recipients),
        "sender_email": endpoint.sender_email,
        "sender_name": endpoint.sender_name or "",
        "smtp_host": endpoint.smtp_host,
        "smtp_port": endpoint.smtp_port,
        "smtp_username": endpoint.smtp_username or "",
        "smtp_security": endpoint.smtp_security,
        "reply_to_field": endpoint.reply_to_field or "email",
        "cap_enabled": endpoint.cap_enabled,
        "cap_verify_url": endpoint.cap_verify_url or "",
        "cap_site_key": endpoint.cap_site_key or "",
        "success_redirect_url": endpoint.success_redirect_url or "",
        "error_redirect_url": endpoint.error_redirect_url or "",
        "allowed_origins": denormalise_origins(endpoint.allowed_origins),
        "max_payload_kb": endpoint.max_payload_kb,
        "is_active": endpoint.is_active,
    }

    return templates.TemplateResponse(
        "endpoints/edit.html",
        {
            "request": request,
            "current_user": current_user,
            "endpoint": endpoint,
            "form": form,
            "error": None,
        },
    )


@router.post("/endpoints/{endpoint_id}/edit")
async def endpoint_edit_submit(
    endpoint_id: int,
    request: Request,
    name: str = Form(...),
    slug: str = Form(...),
    description: str = Form(""),
    recipients: str = Form(...),
    sender_email: str = Form(...),
    sender_name: str = Form(""),
    smtp_host: str = Form(...),
    smtp_port: int = Form(587),
    smtp_username: str = Form(""),
    smtp_password: str = Form(""),
    smtp_security: str = Form("starttls"),
    reply_to_field: str = Form("email"),
    cap_enabled: bool = Form(False),
    cap_verify_url: str = Form(""),
    cap_site_key: str = Form(""),
    cap_secret_key: str = Form(""),
    success_redirect_url: str = Form(""),
    error_redirect_url: str = Form(""),
    allowed_origins: str = Form(""),
    max_payload_kb: int = Form(256),
    is_active: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User | RedirectResponse = Depends(require_user),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    endpoint = get_endpoint_for_user(db, endpoint_id, current_user)

    if not endpoint:
        return RedirectResponse(
            url="/endpoints",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    old_name = endpoint.name
    old_slug = endpoint.slug

    slug = slug.strip().lower()
    recipient_emails = parse_lines(recipients)

    form_data = {
        "name": name,
        "slug": slug,
        "description": description,
        "recipients": recipients,
        "sender_email": sender_email,
        "sender_name": sender_name,
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_username": smtp_username,
        "smtp_security": smtp_security,
        "reply_to_field": reply_to_field,
        "cap_enabled": cap_enabled,
        "cap_verify_url": cap_verify_url,
        "cap_site_key": cap_site_key,
        "success_redirect_url": success_redirect_url,
        "error_redirect_url": error_redirect_url,
        "allowed_origins": allowed_origins,
        "max_payload_kb": max_payload_kb,
        "is_active": is_active,
    }

    if not SLUG_PATTERN.match(slug):
        return templates.TemplateResponse(
            "endpoints/edit.html",
            {
                "request": request,
                "current_user": current_user,
                "endpoint": endpoint,
                "error": "Slug must use lowercase letters, numbers and hyphens only.",
                "form": form_data,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    existing_endpoint = (
        db.query(FormEndpoint)
        .filter(FormEndpoint.slug == slug)
        .filter(FormEndpoint.id != endpoint.id)
        .first()
    )

    if existing_endpoint:
        return templates.TemplateResponse(
            "endpoints/edit.html",
            {
                "request": request,
                "current_user": current_user,
                "endpoint": endpoint,
                "error": "Another endpoint already uses that slug.",
                "form": form_data,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not recipient_emails:
        return templates.TemplateResponse(
            "endpoints/edit.html",
            {
                "request": request,
                "current_user": current_user,
                "endpoint": endpoint,
                "error": "At least one recipient email is required.",
                "form": form_data,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    endpoint.name = name.strip()
    endpoint.slug = slug
    endpoint.description = description.strip() or None
    endpoint.is_active = is_active
    endpoint.success_redirect_url = success_redirect_url.strip() or None
    endpoint.error_redirect_url = error_redirect_url.strip() or None
    endpoint.allowed_origins = normalise_origins(allowed_origins)
    endpoint.reply_to_field = reply_to_field.strip() or None
    endpoint.smtp_host = smtp_host.strip()
    endpoint.smtp_port = smtp_port
    endpoint.smtp_username = smtp_username.strip() or None
    endpoint.smtp_security = smtp_security
    endpoint.sender_email = sender_email.strip()
    endpoint.sender_name = sender_name.strip() or None
    endpoint.cap_enabled = cap_enabled
    endpoint.cap_verify_url = cap_verify_url.strip() or None
    endpoint.cap_site_key = cap_site_key.strip() or None
    endpoint.max_payload_kb = max_payload_kb

    if smtp_password.strip():
        endpoint.smtp_password = encrypt_value(smtp_password.strip())

    if cap_secret_key.strip():
        endpoint.cap_secret_key = encrypt_value(cap_secret_key.strip())

    db.query(FormEndpointRecipient).filter(
        FormEndpointRecipient.endpoint_id == endpoint.id
    ).delete()

    for email in recipient_emails:
        db.add(
            FormEndpointRecipient(
                endpoint_id=endpoint.id,
                email=email,
                recipient_type="to",
                is_active=True,
            )
        )

    create_audit_log(
        db,
        action="Endpoint Updated",
        user=current_user,
        request=request,
        details=f"Updated endpoint: {old_name} ({old_slug}) -> {endpoint.name} ({endpoint.slug})",
    )

    db.commit()

    return RedirectResponse(
        url=f"/endpoints/{endpoint.id}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/endpoints/{endpoint_id}/delete")
async def endpoint_delete_submit(
    endpoint_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | RedirectResponse = Depends(require_user),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    endpoint = get_endpoint_for_user(db, endpoint_id, current_user)

    if endpoint:
        endpoint.is_deleted = True
        endpoint.is_active = False

        create_audit_log(
            db,
            action="Endpoint Deleted",
            user=current_user,
            request=request,
            details=f"Soft deleted endpoint: {endpoint.name} ({endpoint.slug})",
        )

        db.commit()

    return RedirectResponse(
        url="/endpoints",
        status_code=status.HTTP_303_SEE_OTHER,
    )