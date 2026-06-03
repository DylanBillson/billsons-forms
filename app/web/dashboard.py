from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.sessions import SESSION_COOKIE_NAME, get_user_from_session_token
from app.db.models.user import User
from app.db.session import get_db

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def get_current_user(
    request: Request,
    db: Session = Depends(get_db),
) -> User | None:
    session_token = request.cookies.get(SESSION_COOKIE_NAME)
    return get_user_from_session_token(db, session_token)


def require_user(
    current_user: User | None = Depends(get_current_user),
) -> User | RedirectResponse:
    if not current_user:
        return RedirectResponse(
            url="/login",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return current_user


@router.get("/dashboard")
async def dashboard(
    request: Request,
    current_user: User | RedirectResponse = Depends(require_user),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    return templates.TemplateResponse(
        "dashboard/index.html",
        {
            "request": request,
            "current_user": current_user,
        },
    )