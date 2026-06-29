"""Kategori embedding metni üretimi (saf — Postgres/model gerekmez)."""

from app.embed_categories import build_source_text


def test_source_text_ad_ve_veri_turu_birlesir():
    data = {"veri_turu": ["Ad", "Soyad", "TCKN"]}
    assert build_source_text("Kimlik", data) == "Kimlik: Ad, Soyad, TCKN"


def test_source_text_veri_turu_yoksa_sadece_ad():
    assert build_source_text("Diğer", {}) == "Diğer"
