from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, verify_password
from app.auth.sessions import SESSION_COOKIE_NAME, create_user_session, delete_user_session, get_user_from_session_token
from app.core.client_ip import get_client_ip
from app.core.config import settings
from app.core.csrf import require_csrf
from app.db.models.user import User
from app.db.session import get_db
from app.services.audit import create_audit_log
from app.services.rate_limit import check_rate_limit

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")
DUMMY_HASH = hash_password("This is a dummy password value only")


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse("auth/login.html", {"request": request, "error": None})


@router.post("/login", dependencies=[Depends(require_csrf)])
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    client_ip = get_client_ip(request) or "unknown"
    decision = check_rate_limit(
        db, scope="login", identity=client_ip, limit=settings.login_rate_limit_requests,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
    if not decision.allowed:
        return templates.TemplateResponse(
            "auth/login.html", {"request": request, "error": "Too many login attempts. Try again later."},
            status_code=429, headers={"Retry-After": str(decision.retry_after)},
        )
    normalized_username = username.strip()
    user = db.query(User).filter(User.username == normalized_username, User.is_active.is_(True), User.is_deleted.is_(False)).first()
    valid = verify_password(password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid:
        create_audit_log(db, action="Failed Login", username=normalized_username, request=request, details="Invalid credentials.")
        db.commit()
        return templates.TemplateResponse("auth/login.html", {"request": request, "error": "Invalid username or password."}, status_code=401)
    session_token = create_user_session(db, user, ip_address=client_ip, user_agent=request.headers.get("user-agent"))
    create_audit_log(db, action="Login", user=user, request=request, details="User logged in.")
    db.commit()
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(
        SESSION_COOKIE_NAME, session_token, httponly=True, samesite="lax", secure=settings.secure_cookies,
        max_age=settings.session_lifetime_hours * 3600, path="/",
    )
    return response


@router.post("/logout", dependencies=[Depends(require_csrf)])
async def logout(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    user = get_user_from_session_token(db, token)
    if user:
        create_audit_log(db, action="Logout", user=user, request=request, details="User logged out.")
    delete_user_session(db, token)
    db.commit()
    response = RedirectResponse("/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    return response
