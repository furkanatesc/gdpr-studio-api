"""Sağlık uçları — liveness (/healthz) ve readiness (/readyz, DB kontrolü)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_session

router = APIRouter(tags=["health"])
_log = logging.getLogger("app.health")


@router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(session: Session = Depends(get_session)) -> dict:
    try:
        session.execute(text("SELECT 1"))
    except Exception:  # DB hata detayı istemciye sızdırılmaz (bağlantı stringi/host içerebilir)
        _log.exception("readyz DB kontrolü başarısız")
        raise HTTPException(status_code=503, detail="db not ready") from None
    return {"status": "ready"}
