from __future__ import annotations

import ipaddress
import re
import unicodedata


class HostValidationError(ValueError):
    pass


_DNS_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def contains_unsafe_text(value: str) -> bool:
    return any(character.isspace() or unicodedata.category(character).startswith("C") for character in value)


def normalize_hostname(value: str) -> str:
    """Validate and canonicalise one bare DNS hostname, IPv4 or IPv6 address."""
    if not isinstance(value, str) or not value or value != value.strip() or contains_unsafe_text(value):
        raise HostValidationError("Host must not be empty or contain whitespace/control characters.")
    candidate = value
    if candidate.startswith("[") or candidate.endswith("]"):
        if not (candidate.startswith("[") and candidate.endswith("]")):
            raise HostValidationError("IP address brackets are malformed.")
        candidate = candidate[1:-1]
    if not candidate:
        raise HostValidationError("Host must not be empty.")
    if any(token in candidate for token in ("://", "@", "/", "?", "#", "\\")):
        # A colon is valid in IPv6; the tokens above identify non-host syntax.
        raise HostValidationError("Expected a bare hostname or IP address without scheme, credentials or path.")

    looks_like_ip = ":" in candidate or ("." in candidate and all(ch.isdigit() or ch == "." for ch in candidate))
    if looks_like_ip:
        try:
            return ipaddress.ip_address(candidate).compressed.lower()
        except ValueError as exc:
            raise HostValidationError("IP address is malformed.") from exc

    try:
        ascii_host = candidate.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise HostValidationError("Hostname cannot be converted safely with IDNA.") from exc
    if len(ascii_host) > 253:
        raise HostValidationError("Hostname exceeds 253 characters.")
    labels = ascii_host.split(".")
    if any(not label for label in labels):
        raise HostValidationError("Hostname contains an empty DNS label.")
    for label in labels:
        if len(label) > 63:
            raise HostValidationError("Hostname contains a DNS label longer than 63 characters.")
        if not _DNS_LABEL.fullmatch(label):
            raise HostValidationError("DNS labels may contain only letters, digits and internal hyphens.")
    return ascii_host


def host_for_url(host: str) -> str:
    normalized = normalize_hostname(host)
    return f"[{normalized}]" if ":" in normalized else normalized
