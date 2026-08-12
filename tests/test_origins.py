import pytest

from app.core.origins import OriginError, normalize_origin, normalize_origins, origin_is_allowed


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://example.com", "https://example.com"),
        ("HTTPS://EXAMPLE.COM", "https://example.com"),
        ("https://bücher.example", "https://xn--bcher-kva.example"),
        ("http://192.0.2.10", "http://192.0.2.10"),
        ("https://[2001:0DB8::1]", "https://[2001:db8::1]"),
        ("http://example.com:80", "http://example.com"),
        ("https://example.com:443", "https://example.com"),
        ("https://example.com:8443", "https://example.com:8443"),
    ],
)
def test_valid_origins_are_canonical(value, expected):
    assert normalize_origin(value) == expected


def test_origins_are_normalized_and_deduplicated():
    assert normalize_origins(["HTTPS://Example.COM:443", "https://example.com"]) == ["https://example.com"]


@pytest.mark.parametrize(
    "value",
    [
        "null", "*", "ftp://example.com", "https://user@example.com", "https://user:pass@example.com",
        "https://example.com/path", "https://example.com?q=1", "https://example.com#x", "https://example.com/",
        "https://bad_host.example", "https://-bad.example", "https://bad-.example",
        f"https://{'a' * 64}.example", "https://one..example", "https://999.1.1.1",
        "https://[2001:db8:::1]", "https://example.com:0", "https://example.com:65536", "https://example.com:abc",
        " https://example.com", "https://example.com ", "https://exam ple.com", "https://example.com\n",
        "https://example.com\x00",
    ],
)
def test_invalid_origins_are_rejected(value):
    with pytest.raises(OriginError):
        normalize_origin(value)


def test_oversized_hostname_is_rejected():
    value = "https://" + ".".join(["a" * 63] * 5)
    with pytest.raises(OriginError):
        normalize_origin(value)


def test_configured_allowlist_requires_origin():
    assert not origin_is_allowed(None, ["https://example.com"])
