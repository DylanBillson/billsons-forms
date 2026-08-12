from __future__ import annotations

import re
from dataclasses import dataclass
from email.utils import parseaddr
from urllib.parse import urlsplit, urlunsplit

from app.core.config import settings
from app.core.network_validation import HostValidationError, contains_unsafe_text, host_for_url, normalize_hostname
from app.core.origins import OriginError, origins_from_text

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FIELD_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,149}$")


@dataclass
class EndpointValidationResult:
    values: dict[str, object]
    errors: dict[str, str]

    @property
    def is_valid(self) -> bool:
        return not self.errors


def is_email(value: str) -> bool:
    display, parsed = parseaddr(value)
    return not display and parsed == value and len(value) <= 254 and "@" in value and "." in value.rsplit("@", 1)[1]


def validate_http_url(value: str, field: str, errors: dict[str, str], *, cap_siteverify: bool = False) -> str | None:
    original = value
    value = value.strip()
    if not value:
        return None
    if original != value or contains_unsafe_text(value):
        errors[field] = "URL must not contain whitespace or control characters."
        return original
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        errors[field] = "Enter a valid absolute HTTP or HTTPS URL with a valid port."
        return value
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        errors[field] = "Enter a full absolute HTTP or HTTPS URL."
        return value
    if parsed.username is not None or parsed.password is not None:
        errors[field] = "URL credentials are not allowed."
        return value
    if parsed.fragment:
        errors[field] = "URL fragments are not supported."
        return value
    try:
        host = host_for_url(parsed.hostname)
    except HostValidationError as exc:
        errors[field] = f"URL hostname is invalid: {exc}"
        return value
    if port is not None and not 1 <= port <= 65535:
        errors[field] = "URL port must be between 1 and 65535."
        return value
    scheme = parsed.scheme.lower()
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    netloc = host if port is None or default_port else f"{host}:{port}"
    normalized = urlunsplit((scheme, netloc, parsed.path, parsed.query, ""))
    if cap_siteverify:
        meaningful_path = parsed.path.rstrip("/")
        if not meaningful_path or meaningful_path.rsplit("/", 1)[-1].lower() != "siteverify":
            errors[field] = "Use the full CAP siteverify endpoint, for example https://cap.example.com/siteverify."
    return normalized


def validate_endpoint_config(data: dict[str, object], *, existing_smtp_secret: bool = False, existing_cap_secret: bool = False) -> EndpointValidationResult:
    values = dict(data)
    errors: dict[str, str] = {}
    for key in ("name", "slug", "sender_email", "smtp_username", "smtp_security", "reply_to_field", "cap_site_key", "recipients"):
        values[key] = str(values.get(key, "")).strip()
    for key in ("smtp_host", "cap_verify_url", "success_redirect_url", "error_redirect_url", "allowed_origins"):
        values[key] = str(values.get(key, ""))
    values["slug"] = str(values["slug"]).lower()
    if not values["name"]:
        errors["name"] = "Endpoint name is required."
    if not SLUG_PATTERN.fullmatch(str(values["slug"])):
        errors["slug"] = "Use lowercase letters, numbers and single hyphens only."
    recipients = [line.strip() for line in str(values["recipients"]).splitlines() if line.strip()]
    if not recipients:
        errors["recipients"] = "At least one recipient email is required."
    elif any(not is_email(email) for email in recipients):
        errors["recipients"] = "Every recipient must be a valid email address, one per line."
    values["recipient_emails"] = list(dict.fromkeys(email.lower() for email in recipients))
    if not is_email(str(values["sender_email"])):
        errors["sender_email"] = "Enter a valid sender email address."
    try:
        values["smtp_host"] = normalize_hostname(str(values["smtp_host"]))
    except HostValidationError as exc:
        errors["smtp_host"] = f"Enter a valid bare SMTP hostname or IP address: {exc}"
    try:
        port = int(values.get("smtp_port", 0))
        if not 1 <= port <= 65535:
            raise ValueError
        values["smtp_port"] = port
    except (TypeError, ValueError):
        errors["smtp_port"] = "SMTP port must be between 1 and 65535."
    if values["smtp_security"] not in {"none", "starttls", "ssl"}:
        errors["smtp_security"] = "SMTP security must be None, STARTTLS or SSL/TLS."
    if values["reply_to_field"] and not FIELD_PATTERN.fullmatch(str(values["reply_to_field"])):
        errors["reply_to_field"] = "Reply-To field must be a simple form field name."
    cap_enabled = bool(values.get("cap_enabled"))
    values["cap_verify_url"] = validate_http_url(str(values["cap_verify_url"]), "cap_verify_url", errors, cap_siteverify=True)
    if cap_enabled:
        if not values["cap_verify_url"]:
            errors["cap_verify_url"] = "The full CAP siteverify URL is required when CAP is enabled."
        if not values["cap_site_key"]:
            errors["cap_site_key"] = "CAP site key is required when CAP is enabled."
        if not str(values.get("cap_secret_key", "")).strip() and not existing_cap_secret:
            errors["cap_secret_key"] = "CAP secret key is required when CAP is enabled."
    values["success_redirect_url"] = validate_http_url(str(values["success_redirect_url"]), "success_redirect_url", errors)
    values["error_redirect_url"] = validate_http_url(str(values["error_redirect_url"]), "error_redirect_url", errors)
    try:
        values["normalized_origins"] = origins_from_text(str(values["allowed_origins"]))
    except OriginError as exc:
        errors["allowed_origins"] = str(exc)
        values["normalized_origins"] = []
    try:
        max_payload_kb = int(values.get("max_payload_kb", 0))
        if not 1 <= max_payload_kb <= settings.absolute_max_payload_kb:
            raise ValueError
        values["max_payload_kb"] = max_payload_kb
    except (TypeError, ValueError):
        errors["max_payload_kb"] = f"Payload limit must be between 1 and {settings.absolute_max_payload_kb} KB."
    if not str(values.get("smtp_password", "")).strip() and values["smtp_username"] and not existing_smtp_secret:
        errors["smtp_password"] = "SMTP password is required when a username is configured."
    try:
        requests = int(values.get("rate_limit_requests", 30))
        window = int(values.get("rate_limit_window_seconds", 60))
        if not 1 <= requests <= 10000 or not 1 <= window <= 86400:
            raise ValueError
        values["rate_limit_requests"] = requests
        values["rate_limit_window_seconds"] = window
    except (TypeError, ValueError):
        errors["rate_limit_requests"] = "Rate limit must use 1-10,000 requests and a 1-86,400 second window."
    return EndpointValidationResult(values, errors)
