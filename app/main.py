from fastapi import Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from app.api.forms import router as forms_api_router
from app.core.config import settings
from app.core.csrf import CSRFCookieMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.db.session import get_db
from app.services.health import database_ready
from app.web.admin import router as admin_router
from app.web.admin_users import router as admin_users_router
from app.web.auth import router as auth_router
from app.web.dashboard import router as dashboard_router
from app.web.endpoints import router as endpoints_router

app = FastAPI(title=settings.app_name, debug=settings.app_debug)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFCookieMiddleware)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(endpoints_router)
app.include_router(forms_api_router)
app.include_router(admin_router)
app.include_router(admin_users_router)


@app.get("/")
async def root_redirect(request: Request):
    return RedirectResponse("/dashboard")


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


@app.get("/api/ready")
async def readiness_check(db: Session = Depends(get_db)):
    if not database_ready(db):
        return JSONResponse({"status": "not ready", "database": "unavailable"}, status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
    return {"status": "ready", "database": "ok"}
