from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db.models.audit_log import AuditLog
from app.db.models.user import User
from app.db.session import get_db
from app.web.dashboard import require_user

router = APIRouter(prefix="/admin")
templates = Jinja2Templates(directory="app/templates")


def require_admin(
    current_user: User | RedirectResponse = Depends(require_user),
) -> User | RedirectResponse:
    if isinstance(current_user, RedirectResponse):
        return current_user

    if current_user.role != "admin":
        return RedirectResponse(
            url="/dashboard",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return current_user


@router.get("/audit")
async def audit_log_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | RedirectResponse = Depends(require_admin),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    audit_logs = (
        db.query(AuditLog)
        .order_by(AuditLog.created_at.desc())
        .limit(100)
        .all()
    )

    return templates.TemplateResponse(
        "admin/audit.html",
        {
            "request": request,
            "current_user": current_user,
            "audit_logs": audit_logs,
        },
    )