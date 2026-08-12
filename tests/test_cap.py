import httpx
from app.services.cap import CAPStatus, verify_cap_token


async def test_missing_cap_token_is_rejected():
    result = await verify_cap_token("https://cap.example.com/siteverify", "secret", "")
    assert result.status is CAPStatus.REJECTED


async def test_invalid_cap_configuration_is_distinct():
    result = await verify_cap_token("https://cap.example.com", "secret", "token")
    assert result.status is CAPStatus.INVALID_CONFIG


async def test_malformed_cap_hostname_is_not_contacted(monkeypatch):
    class MustNotOpen:
        def __init__(self, *args, **kwargs):
            raise AssertionError("network client must not be created for invalid configuration")

    monkeypatch.setattr(httpx, "AsyncClient", MustNotOpen)
    result = await verify_cap_token("https://bad_host.example/siteverify", "secret", "token")
    assert result.status is CAPStatus.INVALID_CONFIG
