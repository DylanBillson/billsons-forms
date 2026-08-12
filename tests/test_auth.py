from app.auth.passwords import hash_password, password_errors
from app.db.models.user import User
from tests.conftest import csrf_from


def test_password_policy():
    assert password_errors("short", "alice")
    assert not password_errors("correct horse battery staple", "alice")


def test_login_uses_generic_error(client, db):
    page = client.get("/login")
    response = client.post("/login", data={"csrf_token": csrf_from(page), "username": "nobody", "password": "wrong password value"})
    assert response.status_code == 401
    assert "Invalid username or password" in response.text


def test_valid_login_sets_session_cookie(client, db):
    db.add(User(username="alice", display_name="Alice", password_hash=hash_password("correct horse battery staple"), role="admin", is_active=True, is_deleted=False)); db.commit()
    page = client.get("/login")
    response = client.post("/login", data={"csrf_token": csrf_from(page), "username": "alice", "password": "correct horse battery staple"}, follow_redirects=False)
    assert response.status_code == 303
    assert "billsons_forms_session" in response.cookies
