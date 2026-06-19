"""Hafif repository adaptörleri (JSON / sözlük tabanlı).

Bunlar test ve masaüstü (yerel) kullanım içindir. Web tarafının Postgres-tabanlı
repository'leri app katmanında ayrı implemente edilir; ikisi de legal_core'daki
CategoryRepository / BusinessRuleRepository arayüzlerini sağlar.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path


class JsonCategoryRepository:
    """categories.json'ı yükler; anahtarları NFC normalize ederek sunar."""

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._cache: dict[str, dict] | None = None

    def all_categories(self) -> dict[str, dict]:
        if self._cache is None:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._cache = {unicodedata.normalize("NFC", k): v for k, v in raw.items()}
        return self._cache


class DictCategoryRepository:
    """Bellek-içi kategori sözlüğü (test için)."""

    def __init__(self, categories: dict[str, dict]) -> None:
        self._categories = {unicodedata.normalize("NFC", k): v for k, v in categories.items()}

    def all_categories(self) -> dict[str, dict]:
        return self._categories


class DictBusinessRuleRepository:
    """Doküman türü -> kural listesi; 'Tümü' her türde eklenir."""

    def __init__(self, rules_by_type: dict[str, list[str]]) -> None:
        self._rules = rules_by_type

    def business_rules(self, doc_type: str) -> list[str]:
        return list(self._rules.get("Tümü", [])) + list(self._rules.get(doc_type, []))
