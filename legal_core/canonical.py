"""Kanonik eslestirme: norm-exact -> synonym -> ham fallback.

Uydurma yasagi: bilinmeyen deger HAM kalir. Fuzzy eslestirme yok (anlamsal
yanlis eslesme riski nedeniyle kaldirildi).
"""

from __future__ import annotations

import json
from pathlib import Path

from legal_core.normalize import norm

FIELDS = ("veri_turleri", "kategoriler", "kisi_gruplari")

_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "canonical"


class Canonicalizer:
    def __init__(self, tables: dict[str, dict]) -> None:
        self._synonyms: dict[str, dict[str, str]] = {}
        self._norm_maps: dict[str, dict[str, str]] = {}
        for field_name, table in tables.items():
            canonical = table.get("canonical", [])
            self._norm_maps[field_name] = {norm(c): c for c in canonical}
            self._synonyms[field_name] = table.get("synonyms", {})

    def canonicalize(self, value: str, field: str) -> str:
        try:
            n = norm(value)
            if not n:
                return value
            if field not in FIELDS or field not in self._norm_maps:
                return value

            norm_map = self._norm_maps[field]
            if n in norm_map:
                return norm_map[n]

            synonyms = self._synonyms[field]
            if n in synonyms:
                return synonyms[n]

            return value
        except Exception:
            return value

    def canonicalize_list(self, values: list[str], field: str) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            if not value or not value.strip():
                continue
            canonical = self.canonicalize(value, field)
            if canonical in seen:
                continue
            seen.add(canonical)
            result.append(canonical)
        return result


def load_canonicalizer() -> Canonicalizer:
    tables: dict[str, dict] = {}
    for field_name in FIELDS:
        path = _DATA_DIR / f"{field_name}.json"
        tables[field_name] = json.loads(path.read_text(encoding="utf-8"))
    return Canonicalizer(tables)
