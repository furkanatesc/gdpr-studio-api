"""FastAPI uygulaması — modüler monolit giriş noktası."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .modules import generation, grounding, health
from .observability import RequestContextMiddleware, configure_logging, init_sentry

settings = get_settings()

configure_logging(settings.log_level)
init_sentry(settings.sentry_dsn, settings.environment)

app = FastAPI(
    title="KVKK Yönetim API",
    version="0.1.0",
    description="KVKK/GDPR grounded doküman üretimi — legal_core üzerine FastAPI modüler monolit.",
)

# İstek bağlamı (request_id + erişim logu) en dışta; CORS onun içinde.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)

app.include_router(health.router)
app.include_router(grounding.router)
app.include_router(generation.router)


@app.get("/")
def root() -> dict:
    return {"service": "kvkk-yonetim-api", "version": "0.1.0", "docs": "/docs"}
