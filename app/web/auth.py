from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.passwords import verify_password
from app.auth.sessions import (
    SESSION_COOKIE_NAME,
    create_user_session,
    delete_user_session,
    get_user_from_session_token,
)
from app.db.models.user import User
from app.db.session import get_db
from app.services.audit import create_audit_log

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(
        "auth/login.html",
        {
            "request": request,
            "error": None,
        },
    )


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(User.username == username)
        .filter(User.is_active.is_(True))
        .filter(User.is_deleted.is_(False))
        .first()
    )

    if not user or not verify_password(password, user.password_hash):
        create_audit_log(
            db,
            action="Failed Login",
            username=username,
            request=request,
            details="Invalid username or password.",
        )
        db.commit()

        return templates.TemplateResponse(
            "auth/login.html",
            {
                "request": request,
                "error": "Invalid username or password.",
            },
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    session_token = create_user_session(
        db=db,
        user=user,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    create_audit_log(
        db,
        action="Login",
        user=user,
        request=request,
        details="User logged in.",
    )
    db.commit()

    response = RedirectResponse(
        url="/dashboard",
        status_code=status.HTTP_303_SEE_OTHER,
    )

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=True,
        max_age=60 * 60 * 24 * 14,
    )

    return response


@router.post("/logout")
async def logout(
    request: Request,
    db: Session = Depends(get_db),
):
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    current_user = get_user_from_session_token(db, session_token)

    if current_user:
        create_audit_log(
            db,
            action="Logout",
            user=current_user,
            request=request,
            details="User logged out.",
        )

    delete_user_session(db, session_token)
    db.commit()

    response = RedirectResponse(
        url="/login",
        status_code=status.HTTP_303_SEE_OTHER,
    )
    response.delete_cookie(SESSION_COOKIE_NAME)

    return response