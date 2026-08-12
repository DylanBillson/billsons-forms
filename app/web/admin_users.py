from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, password_errors
from app.auth.sessions import delete_user_sessions
from app.core.csrf import require_csrf
from app.db.models.user import User
from app.db.session import get_db
from app.services.audit import create_audit_log
from app.web.admin import require_admin

router = APIRouter(prefix="/admin/users")
templates = Jinja2Templates(directory="app/templates")


VALID_ROLES = {"admin", "user"}


@router.get("")
async def users_index(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | RedirectResponse = Depends(require_admin),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    users = (
        db.query(User)
        .filter(User.is_deleted.is_(False))
        .order_by(User.username.asc())
        .all()
    )

    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "current_user": current_user,
            "users": users,
        },
    )


@router.get("/new")
async def user_create_page(
    request: Request,
    current_user: User | RedirectResponse = Depends(require_admin),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    return templates.TemplateResponse(
        "admin/user_create.html",
        {
            "request": request,
            "current_user": current_user,
            "error": None,
            "form": {},
        },
    )


@router.post("/new", dependencies=[Depends(require_csrf)])
async def user_create_submit(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(...),
    role: str = Form("user"),
    is_active: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User | RedirectResponse = Depends(require_admin),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    username = username.strip()
    display_name = display_name.strip()
    role = role.strip().lower()

    form_data = {
        "username": username,
        "display_name": display_name,
        "role": role,
        "is_active": is_active,
    }

    if role not in VALID_ROLES:
        return templates.TemplateResponse(
            "admin/user_create.html",
            {
                "request": request,
                "current_user": current_user,
                "error": "Role must be admin or user.",
                "form": form_data,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    if not username or not display_name or not password:
        return templates.TemplateResponse(
            "admin/user_create.html",
            {
                "request": request,
                "current_user": current_user,
                "error": "Username, display name and password are required.",
                "form": form_data,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    problems = password_errors(password, username)
    if problems:
        return templates.TemplateResponse(
            "admin/user_create.html",
            {"request": request, "current_user": current_user, "error": " ".join(problems), "form": form_data},
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    existing_user = db.query(User).filter(User.username == username).first()

    if existing_user:
        return templates.TemplateResponse(
            "admin/user_create.html",
            {
                "request": request,
                "current_user": current_user,
                "error": "A user with that username already exists.",
                "form": form_data,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    user = User(
        username=username,
        display_name=display_name,
        password_hash=hash_password(password),
        role=role,
        is_active=is_active,
        is_deleted=False,
    )

    db.add(user)
    db.flush()

    create_audit_log(
        db,
        action="User Created",
        user=current_user,
        request=request,
        details=f"Created user: {user.username} ({user.role})",
    )

    db.commit()

    return RedirectResponse(
        url="/admin/users",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/{user_id}/edit")
async def user_edit_page(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | RedirectResponse = Depends(require_admin),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .filter(User.is_deleted.is_(False))
        .first()
    )

    if not user:
        return RedirectResponse(
            url="/admin/users",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    form = {
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "is_active": user.is_active,
    }

    return templates.TemplateResponse(
        "admin/user_edit.html",
        {
            "request": request,
            "current_user": current_user,
            "user": user,
            "form": form,
            "error": None,
        },
    )


@router.post("/{user_id}/edit", dependencies=[Depends(require_csrf)])
async def user_edit_submit(
    user_id: int,
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    password: str = Form(""),
    role: str = Form("user"),
    is_active: bool = Form(False),
    db: Session = Depends(get_db),
    current_user: User | RedirectResponse = Depends(require_admin),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .filter(User.is_deleted.is_(False))
        .first()
    )

    if not user:
        return RedirectResponse(
            url="/admin/users",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    old_username = user.username

    username = username.strip()
    display_name = display_name.strip()
    role = role.strip().lower()

    form_data = {
        "username": username,
        "display_name": display_name,
        "role": role,
        "is_active": is_active,
    }

    if role not in VALID_ROLES:
        return templates.TemplateResponse(
            "admin/user_edit.html",
            {
                "request": request,
                "current_user": current_user,
                "user": user,
                "error": "Role must be admin or user.",
                "form": form_data,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    existing_user = (
        db.query(User)
        .filter(User.username == username)
        .filter(User.id != user.id)
        .first()
    )

    if existing_user:
        return templates.TemplateResponse(
            "admin/user_edit.html",
            {
                "request": request,
                "current_user": current_user,
                "user": user,
                "error": "Another user already has that username.",
                "form": form_data,
            },
            status_code=status.HTTP_400_BAD_REQUEST,
        )

    password_changed = bool(password.strip())
    was_active = user.is_active
    if password_changed:
        problems = password_errors(password.strip(), username)
        if problems:
            return templates.TemplateResponse(
                "admin/user_edit.html",
                {"request": request, "current_user": current_user, "user": user, "error": " ".join(problems), "form": form_data},
                status_code=status.HTTP_400_BAD_REQUEST,
            )

    user.username = username
    user.display_name = display_name
    user.role = role
    user.is_active = is_active

    if password_changed:
        user.password_hash = hash_password(password.strip())

    if password_changed or (was_active and not is_active):
        delete_user_sessions(db, user.id)

    create_audit_log(
        db,
        action="User Updated",
        user=current_user,
        request=request,
        details=f"Updated user: {old_username} -> {user.username}",
    )

    db.commit()

    return RedirectResponse(
        url="/admin/users",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{user_id}/deactivate", dependencies=[Depends(require_csrf)])
async def user_deactivate_submit(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User | RedirectResponse = Depends(require_admin),
):
    if isinstance(current_user, RedirectResponse):
        return current_user

    user = (
        db.query(User)
        .filter(User.id == user_id)
        .filter(User.is_deleted.is_(False))
        .first()
    )

    if user:
        user.is_active = False
        delete_user_sessions(db, user.id)

        create_audit_log(
            db,
            action="User Deactivated",
            user=current_user,
            request=request,
            details=f"Deactivated user: {user.username}",
        )

        db.commit()

    return RedirectResponse(
        url="/admin/users",
        status_code=status.HTTP_303_SEE_OTHER,
    )
