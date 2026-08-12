import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError
from starlette.requests import Request

from app.core.client_ip import get_client_ip
from app.core.config import Settings, settings


def request_from(peer: str, forwarded: str | None = None) -> Request:
    headers = [] if forwarded is None else [(b"x-forwarded-for", forwarded.encode())]
    return Request({"type": "http", "method": "GET", "path": "/", "client": (peer, 1234), "headers": headers})


def test_forwarded_headers_from_configured_edge_subnet_are_trusted(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxies", "172.30.5.0/24")
    assert get_client_ip(request_from("172.30.5.10", "198.51.100.3")) == "198.51.100.3"


def test_forwarded_headers_from_other_private_subnet_are_ignored(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxies", "172.30.5.0/24")
    assert get_client_ip(request_from("172.30.6.10", "198.51.100.3")) == "172.30.6.10"


def test_direct_arbitrary_client_cannot_spoof_forwarded_ip(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxies", "172.30.5.0/24")
    assert get_client_ip(request_from("203.0.113.10", "198.51.100.3")) == "203.0.113.10"


def test_multiple_forwarded_hops_resolve_from_right_to_left(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxies", "172.30.5.0/24")
    request = request_from("172.30.5.10", "198.51.100.3, 172.30.5.20")
    assert get_client_ip(request) == "198.51.100.3"


def test_malformed_forwarded_chain_is_ignored_safely(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxies", "172.30.5.0/24")
    assert get_client_ip(request_from("172.30.5.10", "198.51.100.3, not-an-ip")) == "172.30.5.10"


def production_settings(trusted_proxies: str) -> Settings:
    return Settings(
        _env_file=None,
        app_env="production",
        app_debug=False,
        app_secret_key="a-production-secret-longer-than-thirty-two-characters",
        app_encryption_key=Fernet.generate_key().decode(),
        base_url="https://forms.example.com",
        database_url="postgresql+psycopg://forms:real-secret@db/forms",
        secure_cookies=True,
        trusted_proxies=trusted_proxies,
    )


@pytest.mark.parametrize("network", ["10.0.0.0/8", "10.0.0.0/15", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7", "0.0.0.0/0"])
def test_production_rejects_overly_broad_trusted_proxy_ranges(network):
    errors = production_settings(network).production_errors()
    assert any("actual edge-network subnet" in error for error in errors)


def test_production_accepts_specific_edge_subnet_and_explicit_ip():
    assert not production_settings("172.30.5.0/24,172.30.5.10").production_errors()


def test_heartbeat_must_be_shorter_than_stale_lock_timeout():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, queue_heartbeat_seconds=300, queue_lock_timeout_seconds=300)
