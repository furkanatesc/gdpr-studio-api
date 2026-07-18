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


class DictProcessRepository:
    """Bellek-içi süreç listesi (test/masaüstü). Öğeler processes.json şeklindedir."""

    def __init__(self, processes: list[dict]) -> None:
        self._items = processes

    def by_sector_and_group(self, sector: str, kisi_grubu: str | None):
        from .models import ProcessRecord

        out = []
        for p in self._items:
            if p["sector"] != sector:
                continue
            if kisi_grubu is not None and p["kisi_grubu"] != kisi_grubu:
                continue
            d = p.get("data", {})
            out.append(
                ProcessRecord(
                    departman=p["departman"], is_sureci=p["is_sureci"],
                    alt_surec=p["alt_surec"], kisi_grubu=p["kisi_grubu"],
                    kategoriler=list(d.get("kategoriler", [])),
                    veri_turleri=list(d.get("veri_turleri", [])),
                    amaclar=list(d.get("amaclar", [])),
                    hukuki_sebepler=list(d.get("hukuki_sebepler", [])),
                    dayanaklar=list(d.get("dayanaklar", [])),
                    saklama_sureleri=list(d.get("saklama_sureleri", [])),
                    islem=list(d.get("islem", [])),
                    ortam_format=list(d.get("ortam_format", [])),
                    konum=list(d.get("konum", [])),
                    idari_tedbirler=list(d.get("idari_tedbirler", [])),
                    teknik_tedbirler=list(d.get("teknik_tedbirler", [])),
                )
            )
        return out
