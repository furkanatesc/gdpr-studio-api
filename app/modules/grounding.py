"""Grounding modülü — kategori referans verisini sunar (web tag listeleri vb.)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_session
from ..redis_client import cache_get_json, cache_set_json
from ..repositories import PostgresCategoryRepository

router = APIRouter(prefix="/api", tags=["grounding"])

_CATEGORIES_CACHE_KEY = "cache:categories"


@router.get("/categories")
def list_categories(session: Session = Depends(get_session)) -> dict:
    """Tüm KVKK kategori adları (grounding referansı). Redis varsa TTL'li cache'lenir."""
    cached = cache_get_json(_CATEGORIES_CACHE_KEY)
    if cached is not None:
        return {"categories": cached}

    repo = PostgresCategoryRepository(session)
    categories = sorted(repo.all_categories().keys())
    cache_set_json(_CATEGORIES_CACHE_KEY, categories, get_settings().categories_cache_ttl_s)
    return {"categories": categories}
