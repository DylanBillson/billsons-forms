from app.auth.passwords import hash_password
from app.auth.sessions import create_user_session, delete_user_sessions, get_user_from_session_token
from app.db.models.user import User


def test_session_lifecycle(db):
    user = User(username="alice", display_name="Alice", password_hash=hash_password("correct horse battery staple"), role="user", is_active=True, is_deleted=False)
    db.add(user); db.commit()
    raw = create_user_session(db, user)
    assert raw not in db.execute(__import__('sqlalchemy').text("select session_token_hash from user_sessions")).scalar_one()
    assert get_user_from_session_token(db, raw).id == user.id
    delete_user_sessions(db, user.id); db.commit()
    assert get_user_from_session_token(db, raw) is None
