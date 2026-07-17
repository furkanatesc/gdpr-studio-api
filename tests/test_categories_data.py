"""Commit'li grounding kataloğu (data/categories.json) doğrulaması.

Zenginleştirme sonrası veri sözleşmesini korur: geçerli JSON, şema anahtarları tam,
çöp token yok, kategori adları NFC (runtime NFC ile arar), ve envanterin kapsadığı
kategorilerde saklama süreleri artık DOLU (kvkk-data-completeness eksiği kapandı).
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from legal_core.adapters import DictCategoryRepository
from legal_core.grounding import Grounding

_PATH = Path(__file__).resolve().parent.parent / "data" / "categories.json"
CATS: dict[str, dict] = json.loads(_PATH.read_text(encoding="utf-8"))

_FIELDS = {
    "veri_turu",
    "kisi_grubu",
    "amaclar",
    "hukuki_sebepler",
    "saklama_sureleri",
    "idari_tedbirler",
    "teknik_tedbirler",
}
_JUNK = {"???", "??", "-", "--", "n/a", "na", "bilinmiyor", "belirsiz", "yok"}

# Envanterden gerçekten dolan kategoriler (insan denetimiyle doğrulandı).
_MUST_HAVE_RETENTION = ["Kimlik", "İletişim", "Finans", "Özlük", "İşlem Güvenliği", "Hukuki İşlem"]


def test_catalog_is_non_empty_dict():
    assert isinstance(CATS, dict) and CATS


def test_schema_keys_present():
    for cat, data in CATS.items():
        missing = _FIELDS - set(data)
        assert not missing, f"{cat} şema anahtarı eksik: {missing}"


def test_no_junk_tokens_anywhere():
    for cat, data in CATS.items():
        for field, vals in data.items():
            if not isinstance(vals, list):
                continue
            junk = [v for v in vals if str(v).strip().lower() in _JUNK]
            assert not junk, f"{cat}.{field} çöp içeriyor: {junk}"


def test_category_names_are_nfc_normalized():
    """Runtime (PostgresCategoryRepository) NFC ile arar → anahtarlar NFC olmalı."""
    for cat in CATS:
        assert unicodedata.normalize("NFC", cat) == cat, f"{cat!r} NFC değil"


def test_no_duplicate_categories_case_insensitive():
    seen: dict[str, str] = {}
    for cat in CATS:
        key = cat.casefold()
        assert key not in seen, f"kategori tekrarı: {cat!r} vs {seen[key]!r}"
        seen[key] = cat


def test_values_are_string_lists():
    for cat, data in CATS.items():
        for field in _FIELDS:
            vals = data[field]
            assert isinstance(vals, list), f"{cat}.{field} liste değil"
            assert all(isinstance(v, str) for v in vals), f"{cat}.{field} string olmayan değer içeriyor"


def test_core_categories_have_retention_after_enrichment():
    """Zenginleştirmenin asıl kazanımı: saklama süreleri artık dolu (uydurma değil, envanterden)."""
    for cat in _MUST_HAVE_RETENTION:
        assert cat in CATS, f"{cat} katalogda yok"
        assert CATS[cat]["saklama_sureleri"], f"{cat} saklama süresi boş"


def test_grounding_resolves_tags_and_surfaces_retention():
    """Uçtan uca: etiket → kategori → saklama süresi (runtime NFC davranışıyla)."""
    cats = {unicodedata.normalize("NFC", k): v for k, v in CATS.items()}
    grounding = Grounding(DictCategoryRepository(cats))
    records = grounding.inventory_rules(["sağlık verisi", "ad-soyad", "e-posta"])
    by_name = {r.kategori: r for r in records}
    assert "Kimlik" in by_name and "İletişim" in by_name and "Sağlık Bilgileri" in by_name
    assert by_name["Kimlik"].saklama_sureleri, "Kimlik grounding'inde saklama süresi gelmeli"
    assert by_name["İletişim"].saklama_sureleri, "İletişim grounding'inde saklama süresi gelmeli"
