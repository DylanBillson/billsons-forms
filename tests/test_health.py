def test_liveness_is_lightweight(client):
    response = client.get("/api/health")
    assert response.status_code == 200 and response.json() == {"status": "ok"}


def test_readiness_checks_database(client):
    response = client.get("/api/ready")
    assert response.status_code == 200 and response.json()["database"] == "ok"
