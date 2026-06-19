"""Grounding modülü — kategori referans verisini sunar (web tag listeleri vb.)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_session
from ..repositories import PostgresCategoryRepository

router = APIRouter(prefix="/api", tags=["grounding"])


@router.get("/categories")
def list_categories(session: Session = Depends(get_session)) -> dict:
    """Tüm KVKK kategori adları (grounding referansı)."""
    repo = PostgresCategoryRepository(session)
    return {"categories": sorted(repo.all_categories().keys())}
