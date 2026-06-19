import unicodedata
from pathlib import Path

import pytest

from legal_core.adapters import DictCategoryRepository, JsonCategoryRepository
from legal_core.grounding import Grounding

FIXTURE = {
    "Kimlik": {
        "veri_turu": ["Ad", "Soyad", "TCKN"],
        "amaclar": ["Kimlik doğrulama"],
        "hukuki_sebepler": ["5/2-ç Hukuki Yükümlülük"],
        "kisi_grubu": ["Müşteri"],
        "saklama_sureleri": [],
    },
    "Sağlık Bilgileri": {
        "veri_turu": ["Sağlık raporu", "Tanı"],
        "amaclar": ["Sağlık hizmeti"],
        "hukuki_sebepler": ["6/3 Sağlık, Cinsel Hayat"],
        "kisi_grubu": ["Hasta"],
        "saklama_sureleri": [],
    },
}


@pytest.fixture
def grounding() -> Grounding:
    return Grounding(DictCategoryRepository(FIXTURE))


def test_sinonim_eslesme(grounding):
    # "Ad-Soyad" sinonim sözlüğünden "Kimlik"e gider.
    assert grounding.resolve_categories(["Ad-Soyad"]) == {"Kimlik"}


def test_dogrudan_kategori_eslesme(grounding):
    assert grounding.resolve_categories(["Kimlik"]) == {"Kimlik"}


def test_veri_turu_altdize_taramasi(grounding):
    # "TCKN" hiçbir sinonim değil; Kimlik.veri_turu içinde alt-dize olarak bulunur.
    assert grounding.resolve_categories(["TCKN"]) == {"Kimlik"}


def test_eslesmeyen_etiket_bos(grounding):
    assert grounding.resolve_categories(["Tamamen Alakasız Etiket"]) == set()


def test_ozel_nitelikli_saglik_sinonimi(grounding):
    assert grounding.resolve_categories(["sağlık verisi"]) == {"Sağlık Bilgileri"}


def test_inventory_rules_alanlari(grounding):
    rules = grounding.inventory_rules(["Ad-Soyad"])
    assert len(rules) == 1
    r = rules[0]
    assert r.kategori == "Kimlik"
    assert "TCKN" in r.veri_turleri
    assert r.hukuki_sebepler == ["5/2-ç Hukuki Yükümlülük"]
    assert r.saklama_sureleri == []  # envanterde boş → uydurulmamalı


# --- Gerçek veri seti (categories.json) ile smoke test ---

REAL = Path(__file__).resolve().parent.parent / "data" / "categories.json"


def test_gercek_veri_nfd_saglik():
    """categories.json'da 'Sağlık Bilgileri' anahtarı NFD tutulur; NFC normalize
    sayesinde sinonim üzerinden çözülmeli ve kayıt dönmeli (regresyon koruması)."""
    g = Grounding(JsonCategoryRepository(REAL))
    matched = g.resolve_categories(["Sağlık verisi"])
    assert any(unicodedata.normalize("NFC", m) == "Sağlık Bilgileri" for m in matched)

    rules = g.inventory_rules(["Sağlık verisi"])
    assert rules and rules[0].hukuki_sebepler  # boş dönmemeli


def test_gercek_veri_kimlik():
    g = Grounding(JsonCategoryRepository(REAL))
    rules = g.inventory_rules(["Ad-Soyad"])
    assert rules and rules[0].kategori == "Kimlik"
    assert "TCKN" in rules[0].veri_turleri
