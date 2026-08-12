from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.security import generate_session_token, hash_token, verify_token
from app.db.models.user import User
from app.db.models.user_session import UserSession
from app.core.config import settings


SESSION_COOKIE_NAME = "billsons_forms_session"


def create_user_session(
    db: Session,
    user: User,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> str:
    raw_token = generate_session_token()

    session = UserSession(
        user_id=user.id,
        session_token_hash=hash_token(raw_token),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.session_lifetime_hours),
        ip_address=ip_address,
        user_agent=user_agent,
    )

    db.add(session)
    db.commit()

    return raw_token


def get_user_from_session_token(
    db: Session,
    raw_token: str | None,
) -> User | None:
    if not raw_token:
        return None

    token_hash = hash_token(raw_token)

    session = (
        db.query(UserSession)
        .filter(UserSession.session_token_hash == token_hash)
        .filter(UserSession.expires_at > datetime.now(timezone.utc))
        .first()
    )

    if not session or not verify_token(raw_token, session.session_token_hash):
        return None

    user = (
        db.query(User)
        .filter(User.id == session.user_id)
        .filter(User.is_active.is_(True))
        .filter(User.is_deleted.is_(False))
        .first()
    )

    return user


def delete_user_session(
    db: Session,
    raw_token: str | None,
) -> None:
    if not raw_token:
        return

    token_hash = hash_token(raw_token)

    session = (
        db.query(UserSession)
        .filter(UserSession.session_token_hash == token_hash)
        .first()
    )

    if session:
        db.delete(session)
        db.commit()


def delete_user_sessions(db: Session, user_id: int) -> None:
    db.query(UserSession).filter(UserSession.user_id == user_id).delete(synchronize_session=False)
