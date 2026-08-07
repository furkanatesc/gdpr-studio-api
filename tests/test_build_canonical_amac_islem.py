import pytest

from scripts.build_canonical_amac_islem.build import (
    build_table,
    parse_source_lines,
    resolve,
)


def test_parse_source_lines_skips_comments_and_blanks():
    text = "# kaynak: X\n\nElde Etme\nSaklama\n  # yorum\nAktarma\n"
    assert parse_source_lines(text) == ["Elde Etme", "Saklama", "Aktarma"]


def test_build_table_shape_and_sorted():
    from legal_core.normalize import norm

    table = build_table(
        canonical_lines=["Saklama", "Elde Etme", "Aktarma"],
        synonyms={"Yayınlama-Alenileştirme": "Aktarma"},
        local_terms=["Saklama", "Yayınlama-Alenileştirme"],
    )
    assert table["canonical"] == ["Aktarma", "Elde Etme", "Saklama"]  # sıralı
    assert table["synonyms"] == {norm("Yayınlama-Alenileştirme"): "Aktarma"}


def test_build_table_orphan_synonym_raises():
    with pytest.raises(ValueError, match="synonym hedefi kanonik değil"):
        build_table(
            canonical_lines=["Aktarma"],
            synonyms={"foo": "Bilinmeyen Kanonik"},
            local_terms=[],
        )


def test_build_table_unresolved_local_term_raises():
    with pytest.raises(ValueError, match="çözülemeyen"):
        build_table(
            canonical_lines=["Aktarma"],
            synonyms={},
            local_terms=["Bilinmeyen Amaç"],
        )


def test_resolve_norm_exact_then_synonym_then_none():
    norm_canonical = {"aktarma": "Aktarma"}
    synonyms = {"yayınlama-alenileştirme": "Aktarma"}
    assert resolve("AKTARMA", norm_canonical, synonyms) == "Aktarma"
    assert resolve("Yayınlama-Alenileştirme", norm_canonical, synonyms) == "Aktarma"
    assert resolve("Bilinmeyen", norm_canonical, synonyms) is None
