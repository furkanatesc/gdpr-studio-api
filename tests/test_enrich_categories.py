"""Grounding katalog zenginleştirme — saf yardımcı birim testleri (CI'da gerçek xlsx istemez)."""

from __future__ import annotations

import json

from scripts.enrich_categories.__main__ import build_enriched
from scripts.enrich_categories.aggregate import aggregate_rows, clean_tokens, merge_catalog
from scripts.enrich_categories.mapping import canonical_category, row_to_record, split_cell
from scripts.enrich_categories.xlsx_reader import parse_shared_strings, parse_worksheet


# ── clean_tokens ─────────────────────────────────────────────────────────────
def test_clean_tokens_removes_junk_and_dedupes():
    got = clean_tokens(["Ad", " Ad ", "ad", "???", "", "n/a", "Soyad", "SOYAD"])
    assert got == ["Ad", "Soyad"]  # ilk yazım korunur, çöp+tekrar atılır


def test_clean_tokens_empty_stays_empty():
    assert clean_tokens([]) == []
    assert clean_tokens(["", "  ", "??", "belirsiz"]) == []


# ── aggregate_rows ───────────────────────────────────────────────────────────
def test_aggregate_groups_by_category_and_unions_fields():
    rows = [
        {"kategori": "Kimlik", "veri_turu": ["Ad"], "saklama_sureleri": ["10 yıl (VUK)"]},
        {"kategori": "Kimlik", "veri_turu": ["Ad", "Soyad"], "saklama_sureleri": ["10 yıl (VUK)"]},
        {"kategori": "İletişim", "veri_turu": ["E-posta"], "saklama_sureleri": []},
    ]
    got = aggregate_rows(rows)
    assert set(got) == {"Kimlik", "İletişim"}
    assert got["Kimlik"]["veri_turu"] == ["Ad", "Soyad"]
    assert got["Kimlik"]["saklama_sureleri"] == ["10 yıl (VUK)"]  # dedupe
    assert got["İletişim"]["saklama_sureleri"] == []  # boş→boş


def test_aggregate_skips_rows_without_category():
    assert aggregate_rows([{"kategori": "", "veri_turu": ["X"]}]) == {}


def test_aggregate_category_keys_case_insensitive():
    rows = [
        {"kategori": "Görsel Ve İşitsel Kayıtlar", "veri_turu": ["Foto"]},
        {"kategori": "Görsel ve İşitsel Kayıtlar", "veri_turu": ["Video"]},
    ]
    got = aggregate_rows(rows)
    assert len(got) == 1  # "Ve"/"ve" aynı kategori
    (name,) = got
    assert name == "Görsel Ve İşitsel Kayıtlar"  # ilk görülen yazım
    assert got[name]["veri_turu"] == ["Foto", "Video"]


# ── merge_catalog ────────────────────────────────────────────────────────────
def test_merge_enriches_existing_and_adds_new():
    base = {"Kimlik": {"veri_turu": ["Ad"], "saklama_sureleri": [], "hukuki_sebepler": ["???"]}}
    src = {
        "Kimlik": {"veri_turu": ["Soyad"], "saklama_sureleri": ["10 yıl (VUK)"], "hukuki_sebepler": ["5/2ç"]},
        "Müşteri İşlem": {"veri_turu": ["Sipariş No"], "saklama_sureleri": ["3 yıl"]},
    }
    got = merge_catalog(base, src)
    assert got["Kimlik"]["veri_turu"] == ["Ad", "Soyad"]
    assert got["Kimlik"]["saklama_sureleri"] == ["10 yıl (VUK)"]  # boş dolduruldu
    assert got["Kimlik"]["hukuki_sebepler"] == ["5/2ç"]  # ??? çöpü temizlendi
    assert "Müşteri İşlem" in got  # yeni kategori eklendi


def test_merge_drops_all_empty_category():
    base = {"Kimlik": {"veri_turu": ["Ad"]}}
    src = {"Genetik Veri": {"veri_turu": [], "saklama_sureleri": []}}  # tümü boş kabuk
    got = merge_catalog(base, src)
    assert "Kimlik" in got
    assert "Genetik Veri" not in got  # boş kabuk eklenmez


# ── mapping ──────────────────────────────────────────────────────────────────
def test_split_cell_multi():
    assert split_cell("Ad, Soyad; TCKN") == ["Ad", "Soyad", "TCKN"]
    assert split_cell("Tek") == ["Tek"]
    assert split_cell("") == []


def test_row_to_record_maps_headers():
    header = ["Kişisel Veri Kategorisi", "Veri Türü", "Azami Süre (Saklama)", "Hukuki Sebep"]
    cells = ["Kimlik", "Ad, Soyad", "10 yıl (VUK)", "5/2ç"]
    rec = row_to_record(header, cells)
    assert rec["kategori"] == "Kimlik"
    assert rec["veri_turu"] == ["Ad", "Soyad"]
    assert rec["saklama_sureleri"] == ["10 yıl (VUK)"]
    assert rec["hukuki_sebepler"] == ["5/2ç"]


def test_row_to_record_none_without_category():
    header = ["Kişisel Veri Kategorisi", "Veri Türü"]
    assert row_to_record(header, ["", "Ad"]) is None


def test_canonical_category_strips_numbering_prefix():
    assert canonical_category("1- Kimlik") == "Kimlik"
    assert canonical_category("12-    Pazarlama") == "Pazarlama"
    assert canonical_category("Kimlik") == "Kimlik"  # öneksiz değişmez


def test_row_to_record_canonicalizes_category():
    header = ["Kişisel Veri Kategorisi", "Veri Türü"]
    rec = row_to_record(header, ["3- Lokasyon", "GPS"])
    assert rec["kategori"] == "Lokasyon"


# ── xlsx_reader (saf parser) ─────────────────────────────────────────────────
def test_parse_shared_strings():
    xml = "<sst><si><t>Kimlik</t></si><si><t>Ad</t></si></sst>"
    assert parse_shared_strings(xml) == ["Kimlik", "Ad"]


def test_parse_worksheet_resolves_shared_and_inline():
    shared = ["Kimlik", "Ad"]
    xml = (
        "<sheetData>"
        '<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
        '<row r="2"><c r="A2" t="inlineStr"><is><t>İletişim</t></is></c></row>'
        "</sheetData>"
    )
    rows = parse_worksheet(xml, shared)
    assert rows[0] == ["Kimlik", "Ad"]
    assert rows[1][0] == "İletişim"


# ── build_enriched (CLI saf çekirdek) ────────────────────────────────────────
def test_build_enriched_merges_base_and_report(tmp_path):
    base = {"Kimlik": {"veri_turu": ["Ad"], "saklama_sureleri": [], "hukuki_sebepler": ["???"]}}
    base_p = tmp_path / "categories.json"
    base_p.write_text(json.dumps(base), encoding="utf-8")
    report = {"Kimlik": {"saklama_sureleri": ["10 yıl (VUK)"], "hukuki_sebepler": ["5/2ç"]}}
    report_p = tmp_path / "report.json"
    report_p.write_text(json.dumps(report), encoding="utf-8")

    got = build_enriched(str(base_p), xlsx_paths=[], report_json_path=str(report_p))
    assert got["Kimlik"]["saklama_sureleri"] == ["10 yıl (VUK)"]
    assert got["Kimlik"]["hukuki_sebepler"] == ["5/2ç"]  # ??? temizlendi
    assert got["Kimlik"]["veri_turu"] == ["Ad"]
