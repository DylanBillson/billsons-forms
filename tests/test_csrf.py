from tests.conftest import csrf_from


def test_missing_csrf_is_rejected(client):
    client.get("/login")
    response = client.post("/login", data={"username": "x", "password": "y"})
    assert response.status_code == 403


def test_csrf_token_from_page_is_accepted(client):
    page = client.get("/login")
    response = client.post("/login", data={"csrf_token": csrf_from(page), "username": "x", "password": "y"})
    assert response.status_code == 401
