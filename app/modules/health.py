"""Sağlık uçları — liveness (/healthz) ve readiness (/readyz, DB kontrolü)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..db import get_session

router = APIRouter(tags=["health"])


@router.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(session: Session = Depends(get_session)) -> dict:
    try:
        session.execute(text("SELECT 1"))
    except Exception as e:  # pragma: no cover
        raise HTTPException(status_code=503, detail=f"db not ready: {e}") from e
    return {"status": "ready"}
