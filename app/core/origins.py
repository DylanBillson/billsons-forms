from __future__ import annotations

import json
from urllib.parse import urlsplit

from app.core.network_validation import HostValidationError, contains_unsafe_text, host_for_url


class OriginError(ValueError):
    pass


def normalize_origin(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or contains_unsafe_text(value):
        raise OriginError("Origin must not be empty or contain whitespace/control characters.")
    raw = value
    if raw.lower() == "null" or "*" in raw:
        raise OriginError("Origin must be a bare HTTP or HTTPS origin; null and wildcards are not allowed.")
    try:
        parsed = urlsplit(raw)
        port = parsed.port
    except ValueError as exc:
        raise OriginError("Origin has an invalid hostname or port.") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise OriginError("Origin scheme must be http or https.")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise OriginError("Origin must contain a hostname and must not contain credentials.")
    if parsed.path or parsed.query or parsed.fragment:
        raise OriginError("Origin must not contain a path, query string or fragment.")
    try:
        host = host_for_url(parsed.hostname)
    except HostValidationError as exc:
        raise OriginError(f"Origin hostname is invalid: {exc}") from exc
    if port is not None and not (1 <= port <= 65535):
        raise OriginError("Origin port must be between 1 and 65535.")
    default_port = (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    return f"{scheme}://{host}{'' if port is None or default_port else f':{port}'}"


def normalize_origins(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = normalize_origin(value)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def origins_from_text(value: str) -> list[str]:
    return normalize_origins([line for line in value.splitlines() if line.strip()])


def origins_from_storage(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return []
    if not isinstance(parsed, list):
        return []
    try:
        return normalize_origins([str(item) for item in parsed])
    except OriginError:
        return []


def origins_to_storage(origins: list[str]) -> str | None:
    normalized = normalize_origins(origins)
    return json.dumps(normalized) if normalized else None


def origin_is_allowed(origin_header: str | None, allowed_origins: list[str]) -> bool:
    if not allowed_origins:
        return True
    if not origin_header:
        return False
    try:
        return normalize_origin(origin_header) in allowed_origins
    except OriginError:
        return False
