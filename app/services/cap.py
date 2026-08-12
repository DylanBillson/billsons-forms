from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import httpx

from app.core.endpoint_validation import validate_http_url


class CAPStatus(str, Enum):
    SUCCESS = "success"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"
    INVALID_CONFIG = "invalid_config"
    MALFORMED_RESPONSE = "malformed_response"


@dataclass(frozen=True)
class CAPResult:
    status: CAPStatus
    diagnostic: str

    @property
    def verified(self) -> bool:
        return self.status is CAPStatus.SUCCESS


async def verify_cap_token(verify_url: str, secret_key: str, token: str) -> CAPResult:
    errors: dict[str, str] = {}
    validate_http_url(verify_url, "url", errors, cap_siteverify=True)
    if errors or not secret_key:
        return CAPResult(CAPStatus.INVALID_CONFIG, errors.get("url", "CAP secret is not configured."))
    if not token:
        return CAPResult(CAPStatus.REJECTED, "CAP token was missing.")
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(verify_url, json={"secret": secret_key, "response": token})
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        return CAPResult(CAPStatus.UNAVAILABLE, f"CAP service unavailable: {type(exc).__name__}")
    if response.status_code >= 500:
        return CAPResult(CAPStatus.UNAVAILABLE, f"CAP service returned HTTP {response.status_code}.")
    if response.status_code >= 400:
        return CAPResult(CAPStatus.MALFORMED_RESPONSE, f"CAP service returned HTTP {response.status_code}.")
    try:
        data = response.json()
    except ValueError:
        return CAPResult(CAPStatus.MALFORMED_RESPONSE, "CAP service returned non-JSON data.")
    if not isinstance(data, dict) or not isinstance(data.get("success"), bool):
        return CAPResult(CAPStatus.MALFORMED_RESPONSE, "CAP response did not contain a boolean success value.")
    return CAPResult(CAPStatus.SUCCESS if data["success"] else CAPStatus.REJECTED, "CAP token accepted." if data["success"] else "CAP token rejected.")


async def test_cap_service(verify_url: str) -> CAPResult:
    errors: dict[str, str] = {}
    validate_http_url(verify_url, "url", errors, cap_siteverify=True)
    if errors:
        return CAPResult(CAPStatus.INVALID_CONFIG, errors["url"])
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(verify_url, json={"secret": "configuration-test", "response": "configuration-test"})
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        return CAPResult(CAPStatus.UNAVAILABLE, f"CAP service unavailable: {type(exc).__name__}")
    if response.status_code >= 500:
        return CAPResult(CAPStatus.UNAVAILABLE, f"CAP service returned HTTP {response.status_code}.")
    try:
        data = response.json()
    except ValueError:
        return CAPResult(CAPStatus.MALFORMED_RESPONSE, "CAP service did not return JSON.")
    if not isinstance(data, dict) or not isinstance(data.get("success"), bool):
        return CAPResult(CAPStatus.MALFORMED_RESPONSE, "CAP response shape was not recognised.")
    return CAPResult(CAPStatus.SUCCESS, "CAP siteverify endpoint is reachable and returned the expected response shape.")
