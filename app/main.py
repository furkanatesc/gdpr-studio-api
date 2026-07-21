"""FastAPI uygulaması — modüler monolit giriş noktası."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .auth.startup_guard import verify_rls_enforcement
from .config import get_settings
from .db import get_engine
from .modules import (
    accounts,
    aydinlatma,
    billing,
    clients,
    compliance,
    generation,
    grounding,
    health,
    inventory,
    invitations,
    memberships,
    processes,
)
from .observability import (
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    configure_logging,
    init_sentry,
)

settings = get_settings()

configure_logging(settings.log_level)
init_sentry(settings.sentry_dsn, settings.environment)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Uygulama yaşam döngüsü: startup'ta RLS zorlama doğrulaması (prod+postgresql).

    Prod'da DB bağlantı rolü SUPERUSER veya BYPASSRLS ise RuntimeError fırlatır
    ve uygulama başlamaz (fail-closed, fail-fast). Dev/test/sqlite'ta no-op.
    """
    verify_rls_enforcement(get_engine(), settings)
    yield


app = FastAPI(
    title="KVKK Yönetim API",
    version="0.1.0",
    description="KVKK/GDPR grounded doküman üretimi — legal_core üzerine FastAPI modüler monolit.",
    lifespan=lifespan,
)

# İstek bağlamı (request_id + erişim logu) en dışta; CORS onun içinde.
# add_middleware sırası ters-uygulanır: en son eklenen en dışta çalışır.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)

app.include_router(health.router)
app.include_router(accounts.router)
app.include_router(invitations.router)
app.include_router(memberships.router)
app.include_router(billing.router)
app.include_router(grounding.router)
app.include_router(generation.router)
app.include_router(compliance.router)
app.include_router(processes.router)
app.include_router(clients.router)
app.include_router(aydinlatma.router)
app.include_router(inventory.router)


@app.get("/")
def root() -> dict:
    return {"service": "kvkk-yonetim-api", "version": "0.1.0", "docs": "/docs"}
