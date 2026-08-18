"""admin-api FastAPI uygulaması — platform admin arka uç servisi."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import get_admin_settings
from .db import get_admin_engine, verify_admin_role_and_head
from .modules.metrics import router as metrics_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_admin_settings()
    if s.environment == "production":
        verify_admin_role_and_head(get_admin_engine(), s)
    yield


app = FastAPI(title="KVKK Yönetim — Admin API", lifespan=lifespan)
app.include_router(metrics_router)


@app.get("/admin/healthz")
def healthz():
    return {"status": "ok"}
