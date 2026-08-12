from __future__ import annotations

import ipaddress

from fastapi import Request

from app.core.config import settings


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    candidate = value.strip()
    if candidate.startswith("[") and "]" in candidate:
        candidate = candidate[1:candidate.index("]")]
    elif candidate.count(":") == 1 and "." in candidate:
        candidate = candidate.rsplit(":", 1)[0]
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        return None


def _is_trusted(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return any(address in network for network in settings.trusted_proxy_networks)


def get_client_ip(request: Request) -> str | None:
    peer = _parse_ip(request.client.host) if request.client else None
    if peer is None:
        return None
    if not _is_trusted(peer):
        return str(peer)
    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        real_ip = _parse_ip(request.headers.get("x-real-ip", ""))
        return str(real_ip or peer)
    chain = [_parse_ip(part) for part in forwarded.split(",")]
    if any(item is None for item in chain):
        return str(peer)
    for address in reversed([*chain, peer]):
        if address is not None and not _is_trusted(address):
            return str(address)
    return str(chain[0] or peer)
