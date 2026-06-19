"""FastAPI uygulaması — modüler monolit giriş noktası."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .modules import generation, grounding, health

settings = get_settings()

app = FastAPI(
    title="KVKK Yönetim API",
    version="0.1.0",
    description="KVKK/GDPR grounded doküman üretimi — legal_core üzerine FastAPI modüler monolit.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(grounding.router)
app.include_router(generation.router)


@app.get("/")
def root() -> dict:
    return {"service": "kvkk-yonetim-api", "version": "0.1.0", "docs": "/docs"}
