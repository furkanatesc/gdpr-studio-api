"""Aydınlatma metni boilerplate şablonu testleri (avukat onayına tabi taslak)."""

from __future__ import annotations

from legal_core.boilerplate import load_boilerplate

_KEYS = {"tanimlar", "kaynaklar", "ortak_hukumler", "haklar_m11", "basvuru_usulu"}


def test_returns_exactly_five_keys():
    data = load_boilerplate()
    assert set(data) == _KEYS


def test_all_sections_are_non_empty_prose():
    data = load_boilerplate()
    for key, value in data.items():
        assert isinstance(value, str), f"{key} string değil"
        assert value.strip(), f"{key} boş"


def test_tanimlar_refers_to_madde_3():
    data = load_boilerplate()
    assert "m.3" in data["tanimlar"] or "madde 3" in data["tanimlar"].lower()


def test_haklar_m11_refers_to_madde_11():
    data = load_boilerplate()
    assert "m.11" in data["haklar_m11"] or "madde 11" in data["haklar_m11"].lower()


def test_basvuru_usulu_refers_to_madde_13():
    data = load_boilerplate()
    assert "m.13" in data["basvuru_usulu"] or "madde 13" in data["basvuru_usulu"].lower()


def test_haklar_m11_lists_all_nine_rights():
    text = load_boilerplate()["haklar_m11"].lower()
    distinctive_terms = [
        "işlenip işlenmediğini öğrenme",
        "bilgi talep etme",
        "amacını",
        "aktarıldığı üçüncü kişileri",
        "düzeltilmesini",
        "silinmesini",
        "üçüncü kişilere bildirilmesini",
        "otomatik",
        "zararın giderilmesini",
    ]
    for term in distinctive_terms:
        assert term in text, f"haklar_m11 içinde beklenen ifade eksik: {term!r}"


def test_no_placeholder_text():
    data = load_boilerplate()
    for key, value in data.items():
        assert "[Avukat tarafından doldurulacak]" not in value, f"{key} yer tutucu içeriyor"


def test_no_unapproved_article_numbers():
    """Brief'te onaylanmayan madde numaraları (ör. m.9, m.20) metinde geçmemeli."""
    data = load_boilerplate()
    forbidden = ["m.9", "m.20", "m.21", "m.22"]
    for key, value in data.items():
        for bad in forbidden:
            assert bad not in value, f"{key} onaysız madde atfı içeriyor: {bad}"
