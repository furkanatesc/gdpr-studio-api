"""Kanonik sözlük JSON'ları (veri_turleri/kategoriler/kisi_gruplari) doğrulaması.

Kaynak: docs/deepsearch-envanter-zenginlestirme-promptu.md — birebir transkript.
"""

from __future__ import annotations

import json
from pathlib import Path

from legal_core.normalize import norm

_DIR = Path(__file__).resolve().parent.parent / "data" / "canonical"

_FILES = {
    "kategoriler": ("kategoriler.json", 30),
    "kisi_gruplari": ("kisi_gruplari.json", 30),
    "veri_turleri": ("veri_turleri.json", 120),
}


def _load(name: str) -> dict:
    filename, _ = _FILES[name]
    return json.loads((_DIR / filename).read_text(encoding="utf-8"))


def test_files_exist_and_parse():
    for name in _FILES:
        data = _load(name)
        assert isinstance(data, dict)


def test_schema_shape():
    for name in _FILES:
        data = _load(name)
        assert "canonical" in data and "synonyms" in data
        assert isinstance(data["canonical"], list) and data["canonical"]
        assert all(isinstance(v, str) for v in data["canonical"])
        assert isinstance(data["synonyms"], dict)


def test_count_thresholds():
    for name, (_, minimum) in _FILES.items():
        data = _load(name)
        assert len(data["canonical"]) >= minimum, f"{name}: {len(data['canonical'])} < {minimum}"


def test_no_duplicates_in_canonical():
    for name in _FILES:
        data = _load(name)
        values = data["canonical"]
        assert len(values) == len(set(values)), f"{name}: tekrar eden değer var"


def test_spot_check_kategoriler():
    data = _load("kategoriler")
    for v in ("Kimlik", "Sağlık Bilgileri"):
        assert v in data["canonical"]


def test_spot_check_kisi_gruplari():
    data = _load("kisi_gruplari")
    for v in ("Aktif Çalışan", "Site Ziyaretçisi"):
        assert v in data["canonical"]


def test_spot_check_veri_turleri():
    data = _load("veri_turleri")
    for v in ("Ad-soyad", "T.C. kimlik no", "IP adresi"):
        assert v in data["canonical"]


def test_synonyms_target_existing_canonical_values():
    for name in _FILES:
        data = _load(name)
        canonical_set = set(data["canonical"])
        for key, target in data["synonyms"].items():
            assert target in canonical_set, f"{name}: synonym {key!r} -> {target!r} kanonik değil"


def test_synonym_keys_are_already_normalized():
    for name in _FILES:
        data = _load(name)
        for key in data["synonyms"]:
            assert norm(key) == key, f"{name}: synonym anahtarı {key!r} normalize değil"
