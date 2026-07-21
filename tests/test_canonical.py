"""Canonicalizer birim testleri: norm-exact -> synonym -> ham fallback."""

from __future__ import annotations

import pytest

from legal_core.canonical import Canonicalizer, load_canonicalizer

TABLES = {
    "veri_turleri": {
        "canonical": ["Ad-soyad", "T.C. kimlik no", "IP adresi"],
        "synonyms": {"tckn": "T.C. kimlik no"},
    }
}


@pytest.fixture
def c() -> Canonicalizer:
    return Canonicalizer(TABLES)


def test_norm_exact(c: Canonicalizer):
    assert c.canonicalize("AD-SOYAD", "veri_turleri") == "Ad-soyad"


def test_synonym(c: Canonicalizer):
    assert c.canonicalize("TCKN", "veri_turleri") == "T.C. kimlik no"


def test_canonicalize_yakin_ama_norm_esit_degil_ham_kalir(c: Canonicalizer):
    assert c.canonicalize("Ad soyad", "veri_turleri") == "Ad soyad"


def test_difflib_esik_altinda_ham_doner(c: Canonicalizer):
    value = "Filanca alakasiz deger"
    assert c.canonicalize(value, "veri_turleri") == value


def test_bilinmeyen_field_passthrough(c: Canonicalizer):
    assert c.canonicalize("x", "amaclar") == "x"


def test_bos_deger(c: Canonicalizer):
    assert c.canonicalize("", "veri_turleri") == ""


def test_canonicalize_list_dedup_sira_ve_bos_atma(c: Canonicalizer):
    result = c.canonicalize_list(["AD-SOYAD", "ad-soyad", ""], "veri_turleri")
    assert result == ["Ad-soyad"]


def test_load_canonicalizer_gercek_dosya():
    real = load_canonicalizer()
    assert real.canonicalize("ıp adresi", "veri_turleri") == "IP adresi"
    assert real.canonicalize("IP ADRESI", "veri_turleri") == "IP adresi"
