from app.core.origins import origins_to_storage


def test_dynamic_preflight(client, endpoint, db):
    endpoint.allowed_origins = origins_to_storage(["https://site.example"]); db.commit()
    response = client.options("/api/v1/forms/contact", headers={"Origin": "https://site.example", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == "https://site.example"
    assert response.headers["vary"] == "Origin"


def test_disallowed_preflight_has_no_allow_origin(client, endpoint, db):
    endpoint.allowed_origins = origins_to_storage(["https://site.example"]); db.commit()
    response = client.options("/api/v1/forms/contact", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"})
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers
