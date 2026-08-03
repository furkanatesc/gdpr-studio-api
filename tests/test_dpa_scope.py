from legal_core.dpa_scope import distinct_aktarim_adlari, resolve_dpa_scope
from legal_core.models import ProcessRecord


def _rec(**kw):
    base = dict(departman="D", is_sureci="S", alt_surec="A", kisi_grubu="Çalışan")
    base.update(kw)
    return ProcessRecord(**base)


def test_resolve_matches_by_normalized_aktarim():
    recs = [
        _rec(aktarim=["Muhasebe Bürosu"], kategoriler=["Kimlik"], amaclar=["Bordro"]),
        _rec(aktarim=["SGK"], kategoriler=["Sağlık"]),
    ]
    scope = resolve_dpa_scope(recs, aliases=["muhasebe bürosu"])  # norm eşleşir
    assert len(scope.eslesen_surecler) == 1
    assert scope.kategoriler == ["Kimlik"]
    assert scope.amaclar == ["Bordro"]


def test_resolve_unions_and_dedupes():
    recs = [
        _rec(aktarim=["Bulut"], kategoriler=["Kimlik"], teknik_tedbirler=["Şifreleme"]),
        _rec(aktarim=["Bulut"], kategoriler=["Kimlik", "İletişim"], teknik_tedbirler=["Şifreleme", "Yedekleme"]),
    ]
    scope = resolve_dpa_scope(recs, aliases=["Bulut"])
    assert len(scope.eslesen_surecler) == 2
    assert scope.kategoriler == ["Kimlik", "İletişim"]
    assert scope.teknik_tedbirler == ["Şifreleme", "Yedekleme"]


def test_resolve_empty_when_no_alias_match():
    recs = [_rec(aktarim=["Bulut"])]
    assert resolve_dpa_scope(recs, aliases=["Muhasebe"]).eslesen_surecler == []
    assert resolve_dpa_scope(recs, aliases=[]).eslesen_surecler == []


def test_distinct_aktarim_preserves_first_display_dedupe_by_norm():
    recs = [
        _rec(aktarim=["Muhasebe Bürosu", "SGK"]),
        _rec(aktarim=["muhasebe bürosu", "Bulut"]),
    ]
    adlar = distinct_aktarim_adlari(recs)
    assert adlar == ["Muhasebe Bürosu", "SGK", "Bulut"]  # ilk görünen yazım korunur
