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


def test_eslesmeyen_deger_ham_doner(c: Canonicalizer):
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


def test_canonicalize_amac_islem_exact_synonym_ham():
    canon = load_canonicalizer()
    # exact (norm-eşleşme)
    assert canon.canonicalize("saklama", "islem") == "Saklama"
    # synonym varyantı -> kanonik (küratörlü)
    assert canon.canonicalize("Yayınlama-Alenileştirme", "islem") == "Alenileştirme"
    # uydurma yok: bilinmeyen HAM kalır
    assert canon.canonicalize("Zıpzıp İşlemi", "islem") == "Zıpzıp İşlemi"


def test_seed_islem_variants_all_resolve():
    canon = load_canonicalizer()
    variants = [
        "Elde Etme", "Saklama", "Kullanma", "Doğrulama", "Oluşturma",
        "Üretme", "Aktarma", "Alenileştirme", "Yayınlama-Alenileştirme",
        "Aktarma/ Alenileştirme",
    ]
    for v in variants:
        out = canon.canonicalize(v, "islem")
        assert out in set(canon._norm_maps["islem"].values()), f"{v!r} -> {out!r} kanonik değil"


def test_seed_amac_terms_all_resolve():
    import json
    from pathlib import Path

    canon = load_canonicalizer()
    processes = json.loads(
        (Path(__file__).resolve().parent.parent / "data" / "processes.json").read_text("utf-8")
    )
    seed_amac = {a for r in processes for a in (r.get("data", {}).get("amaclar") or [])}
    canonical_amac = set(canon._norm_maps["amaclar"].values())
    for a in seed_amac:
        assert canon.canonicalize(a, "amaclar") in canonical_amac, f"{a!r} kanoniğe çözülmedi"
