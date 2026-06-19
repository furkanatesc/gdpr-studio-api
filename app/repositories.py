"""Postgres-tabanlı repository implementasyonları (legal_core arayüzleri)."""

from __future__ import annotations

import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import BusinessRule, Category


class PostgresCategoryRepository:
    """legal_core.CategoryRepository — kategorileri Postgres'ten sunar."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def all_categories(self) -> dict[str, dict]:
        rows = self._session.execute(select(Category.name, Category.data)).all()
        return {unicodedata.normalize("NFC", name): data for name, data in rows}


class PostgresBusinessRuleRepository:
    """legal_core.BusinessRuleRepository — türe özel + 'Tümü' kuralları döndürür."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def business_rules(self, doc_type: str) -> list[str]:
        stmt = select(BusinessRule.kural_metni).where(
            BusinessRule.dokuman_turu.in_(["Tümü", doc_type])
        )
        return [r[0] for r in self._session.execute(stmt).all()]
