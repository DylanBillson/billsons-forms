import pytest

from app.auth.passwords import hash_password
from app.auth.sessions import SESSION_COOKIE_NAME, create_user_session
from app.core.endpoint_validation import validate_endpoint_config, validate_http_url
from app.db.models.user import User
from tests.conftest import csrf_from


def valid_data():
    return {
        "name": "Contact", "slug": "contact", "recipients": "a@example.com", "sender_email": "forms@example.com",
        "smtp_host": "smtp.example.com", "smtp_port": 587, "smtp_security": "starttls", "smtp_username": "",
        "smtp_password": "", "reply_to_field": "email", "cap_enabled": False, "cap_verify_url": "",
        "cap_site_key": "", "cap_secret_key": "", "success_redirect_url": "", "error_redirect_url": "",
        "allowed_origins": "https://example.com", "max_payload_kb": 256,
        "rate_limit_requests": 30, "rate_limit_window_seconds": 60,
    }


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("SMTP.EXAMPLE.COM", "smtp.example.com"),
        ("192.0.2.15", "192.0.2.15"),
        ("2001:0DB8::5", "2001:db8::5"),
        ("münchen.example", "xn--mnchen-3ya.example"),
    ],
)
def test_smtp_hostname_types_are_validated_and_normalized(host, expected):
    data = valid_data(); data["smtp_host"] = host
    result = validate_endpoint_config(data)
    assert "smtp_host" not in result.errors
    assert result.values["smtp_host"] == expected


@pytest.mark.parametrize(
    "host",
    ["bad_host.example", "-bad.example", "bad-.example", "one..example", "999.1.1.1", "2001:db8:::1", "smtp://example.com", "user@example.com", "example.com/path", " example.com", "example.com\n", "a" * 64 + ".example"],
)
def test_malformed_smtp_hosts_have_field_error_and_preserve_input(host):
    data = valid_data(); data["smtp_host"] = host
    result = validate_endpoint_config(data)
    assert "smtp_host" in result.errors
    assert result.values["smtp_host"] == host


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("HTTPS://EXAMPLE.COM:443/thanks?source=form", "https://example.com/thanks?source=form"),
        ("http://192.0.2.2:8080/path", "http://192.0.2.2:8080/path"),
        ("https://[2001:db8::1]/done", "https://[2001:db8::1]/done"),
        ("https://bücher.example/danke", "https://xn--bcher-kva.example/danke"),
    ],
)
def test_redirect_urls_allow_paths_queries_and_are_canonical(value, expected):
    errors = {}
    assert validate_http_url(value, "redirect", errors) == expected
    assert not errors


@pytest.mark.parametrize(
    "value",
    ["/relative", "ftp://example.com/x", "https://user@example.com/x", "https://bad_host/x", "https://example.com:abc/x", "https://example.com/x#fragment", " https://example.com/x", "https://exam ple.com/x"],
)
def test_invalid_redirects_have_field_specific_errors(value):
    errors = {}
    assert validate_http_url(value, "success_redirect_url", errors) is not None
    assert "success_redirect_url" in errors


@pytest.mark.parametrize("url", ["https://cap.example.com", "https://cap.example.com/verify", "https://cap.example.com/siteverify/extra", "/siteverify", "https://bad_host/siteverify"])
def test_cap_requires_valid_full_siteverify_endpoint(url):
    data = valid_data()
    data.update(cap_enabled=True, cap_verify_url=url, cap_site_key="site", cap_secret_key="secret")
    result = validate_endpoint_config(data)
    assert "cap_verify_url" in result.errors
    assert "siteverify" in result.errors["cap_verify_url"].lower() or "hostname" in result.errors["cap_verify_url"].lower() or "absolute" in result.errors["cap_verify_url"].lower()


def test_valid_cap_siteverify_url_is_canonicalized():
    data = valid_data()
    data.update(cap_enabled=True, cap_verify_url="HTTPS://CAP.EXAMPLE.COM:443/api/siteverify", cap_site_key="site", cap_secret_key="secret")
    result = validate_endpoint_config(data)
    assert result.is_valid
    assert result.values["cap_verify_url"] == "https://cap.example.com/api/siteverify"


def test_field_errors_preserve_submitted_values():
    data = valid_data(); data.update(smtp_host=" bad_host ", success_redirect_url=" bad url ")
    result = validate_endpoint_config(data)
    assert set(("smtp_host", "success_redirect_url")).issubset(result.errors)
    assert result.values["smtp_host"] == " bad_host "
    assert result.values["success_redirect_url"] == " bad url "


def test_valid_endpoint_configuration_is_normalized():
    result = validate_endpoint_config(valid_data())
    assert result.is_valid
    assert result.values["normalized_origins"] == ["https://example.com"]


def test_management_create_reuses_validation_and_preserves_flow(client, db):
    user = User(username="admin", display_name="Admin", password_hash=hash_password("correct horse battery staple"), role="admin", is_active=True, is_deleted=False)
    db.add(user); db.commit()
    client.cookies.set(SESSION_COOKIE_NAME, create_user_session(db, user), domain="testserver")
    page = client.get("/endpoints/new")
    response = client.post("/endpoints/new", data={
        "csrf_token": csrf_from(page), "name": "Contact", "slug": "contact", "recipients": "team@example.com",
        "sender_email": "forms@example.com", "smtp_host": "smtp.example.com", "smtp_port": "587",
        "smtp_security": "starttls", "reply_to_field": "email", "allowed_origins": "https://example.com",
        "max_payload_kb": "256", "rate_limit_requests": "30", "rate_limit_window_seconds": "60",
        "rate_limit_enabled": "true", "is_active": "true",
    }, follow_redirects=False)
    assert response.status_code == 303
