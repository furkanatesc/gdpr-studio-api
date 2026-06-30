"""Semantik fallback (4. aşama) — legal_core saf çekirdek, stub matcher ile."""

from legal_core.grounding import Grounding

FIXTURE = {
    "Kimlik": {"veri_turu": ["Ad", "Soyad", "TCKN"], "amaclar": [], "hukuki_sebepler": []},
    "İletişim": {"veri_turu": ["E-posta", "Telefon"], "amaclar": [], "hukuki_sebepler": []},
}


class _DictRepo:
    def __init__(self, cats):
        self._cats = cats

    def all_categories(self):
        return self._cats


class _StubMatcher:
    """Sabit eşleme + çağrı kaydı (exact-first doğrulaması için)."""

    def __init__(self, mapping):
        self._mapping = mapping  # norm-edilmemiş ham tag -> (kategori, skor) | None
        self.calls: list[str] = []

    def best_category(self, tag):
        self.calls.append(tag)
        return self._mapping.get(tag)


def _grounding(matcher=None):
    return Grounding(_DictRepo(FIXTURE), matcher=matcher)


def test_matcher_none_korur_mevcut_davranis():
    # Bilinmeyen etiket, matcher yok → eşleşme yok (mevcut davranış birebir).
    g = _grounding(matcher=None)
    assert g.resolve_categories(["konum verisi"]) == set()


def test_deterministik_eslesen_etiket_matcher_cagirmaz():
    # "Kimlik" doğrudan kategori adı (2. aşama) → matcher HİÇ çağrılmamalı (exact-first).
    m = _StubMatcher({"Kimlik": ("İletişim", 0.99)})
    g = _grounding(matcher=m)
    assert g.resolve_categories(["Kimlik"]) == {"Kimlik"}
    assert m.calls == []


def test_deterministik_bos_matcher_eslestirirse_eklenir():
    # "konum verisi" 1-3'e uymaz; matcher ("İletişim", skor) dönerse eklenir.
    m = _StubMatcher({"konum verisi": ("İletişim", 0.85)})
    g = _grounding(matcher=m)
    assert g.resolve_categories(["konum verisi"]) == {"İletişim"}
    assert m.calls == ["konum verisi"]


def test_matcher_none_donerse_etiket_duser():
    # Eşik-altı → matcher None → etiket eşleşmez (uydurma yok).
    m = _StubMatcher({"konum verisi": None})
    g = _grounding(matcher=m)
    assert g.resolve_categories(["konum verisi"]) == set()
    assert m.calls == ["konum verisi"]


def test_karisik_etiketler():
    # "Kimlik" deterministik + "konum verisi" semantik + "xyzxyz" eşleşmez.
    m = _StubMatcher({"konum verisi": ("İletişim", 0.9), "xyzxyz": None})
    g = _grounding(matcher=m)
    assert g.resolve_categories(["Kimlik", "konum verisi", "xyzxyz"]) == {"Kimlik", "İletişim"}
    assert "Kimlik" not in m.calls  # exact-first: deterministik olan matcher'a gitmez
