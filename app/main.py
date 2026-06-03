from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.forms import router as forms_api_router
from app.core.config import settings
from app.web.admin import router as admin_router
from app.web.admin_users import router as admin_users_router
from app.web.auth import router as auth_router
from app.web.dashboard import router as dashboard_router
from app.web.endpoints import router as endpoints_router

app = FastAPI(
    title=settings.app_name,
    debug=settings.app_debug,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(endpoints_router)
app.include_router(forms_api_router)
app.include_router(admin_router)
app.include_router(admin_users_router)

@app.get("/")
async def root_redirect(request: Request):
    return RedirectResponse(url="/dashboard")


@app.get("/api/health")
async def health_check():
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
    }