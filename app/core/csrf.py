from __future__ import annotations

import hmac
import secrets
from hashlib import sha256

from fastapi import Form, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

CSRF_COOKIE_NAME = "billsons_forms_csrf"


def csrf_token(seed: str) -> str:
    return hmac.new(settings.app_secret_key.encode(), seed.encode(), sha256).hexdigest()


class CSRFCookieMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        seed = request.cookies.get(CSRF_COOKIE_NAME) or secrets.token_urlsafe(32)
        request.state.csrf_token = csrf_token(seed)
        response = await call_next(request)
        if CSRF_COOKIE_NAME not in request.cookies:
            response.set_cookie(
                CSRF_COOKIE_NAME,
                seed,
                secure=settings.secure_cookies,
                httponly=True,
                samesite="strict",
                path="/",
            )
        return response


async def require_csrf(request: Request, csrf_token_value: str = Form("", alias="csrf_token")) -> None:
    seed = request.cookies.get(CSRF_COOKIE_NAME)
    if not seed or not secrets.compare_digest(csrf_token(seed), csrf_token_value):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token.")
