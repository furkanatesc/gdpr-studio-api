"""admin-api FastAPI uygulaması — platform admin arka uç servisi."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import get_admin_settings
from .db import get_admin_engine, verify_admin_role_and_head
from .middleware import AdminRateLimitMiddleware
from .modules.audit import router as audit_router
from .modules.impersonation import router as impersonation_router
from .modules.metrics import router as metrics_router
from .modules.tenants import router as tenants_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_admin_settings()
    if s.environment == "production":
        verify_admin_role_and_head(get_admin_engine(), s)
    yield


app = FastAPI(title="KVKK Yönetim — Admin API", lifespan=lifespan)
app.add_middleware(AdminRateLimitMiddleware)
app.include_router(audit_router)
app.include_router(metrics_router)
app.include_router(tenants_router)
app.include_router(impersonation_router)


@app.get("/admin/healthz")
def healthz():
    return {"status": "ok"}
