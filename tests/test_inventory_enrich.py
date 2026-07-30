from legal_core.adapters import DictProcessRepository
from legal_core.inventory_enrich import InventorySuggestion, enrich_inventory
from legal_core.models import ProcessRecord


def _rec(**kw):
    base = dict(departman="IK", is_sureci="Ozluk", alt_surec="Bordro", kisi_grubu="Calisan")
    base.update(kw)
    return ProcessRecord(**base)


def _grounding(kisi_grubu="Calisan", **data):
    return {
        "sector": "otel", "kisi_grubu": kisi_grubu, "departman": "IK",
        "is_sureci": "Ozluk", "alt_surec": "Bordro",
        "data": {"kategoriler": ["Kimlik"], **data},
    }


def test_suggests_grounding_value_for_empty_field():
    repo = DictProcessRepository([_grounding(saklama_sureleri=["10 yil"])])
    rec = _rec(kategoriler=["Kimlik"], saklama_sureleri=[])
    out = enrich_inventory([rec], "otel", repo)
    assert len(out) == 1
    assert isinstance(out[0], InventorySuggestion)
    assert out[0].index == 0
    assert out[0].oneriler["saklama_sureleri"] == ["10 yil"]


def test_no_suggestion_for_filled_field():
    repo = DictProcessRepository([_grounding(hukuki_sebepler=["Grounding Sebep"])])
    rec = _rec(kategoriler=["Kimlik"], hukuki_sebepler=["Mevcut Sebep"], saklama_sureleri=["1 yil"],
               amaclar=["x"], veri_turleri=["y"])
    out = enrich_inventory([rec], "otel", repo)
    # tum enrichable alanlar dolu -> hukuki_sebepler onerilmez; aktarim bos -> elle_alanlar
    assert out == [InventorySuggestion(index=0, departman="IK", is_sureci="Ozluk",
                                       alt_surec="Bordro", kisi_grubu="Calisan",
                                       oneriler={}, elle_alanlar=["aktarim"])]


def test_no_fabrication_only_grounding_values():
    repo = DictProcessRepository([_grounding(amaclar=["Bordro", "Ozluk"])])
    rec = _rec(kategoriler=["Kimlik"], amaclar=[])
    out = enrich_inventory([rec], "otel", repo)
    assert set(out[0].oneriler["amaclar"]) <= {"Bordro", "Ozluk"}


def test_precise_to_loose_fallback():
    # Hassas havuz (kategori kesisimi) saklama bos birakir; gevsek havuz doldurur.
    repo = DictProcessRepository([
        _grounding(kategoriler=["Kimlik"]),                       # kesisen ama saklama yok
        _grounding(kategoriler=["Finans"], saklama_sureleri=["5 yil"]),  # kesismeyen ama saklama var
    ])
    rec = _rec(kategoriler=["Kimlik"], saklama_sureleri=[])
    out = enrich_inventory([rec], "otel", repo)
    assert out[0].oneriler["saklama_sureleri"] == ["5 yil"]


def test_aktarim_never_suggested_but_reported_elle():
    repo = DictProcessRepository([_grounding(aktarim=["Yurt disi"])])
    rec = _rec(kategoriler=["Kimlik"], amaclar=["x"], veri_turleri=["y"],
               hukuki_sebepler=["z"], saklama_sureleri=["1 yil"], aktarim=[])
    out = enrich_inventory([rec], "otel", repo)
    assert "aktarim" not in out[0].oneriler
    assert out[0].elle_alanlar == ["aktarim"]


def test_no_row_when_nothing_to_offer():
    repo = DictProcessRepository([])
    rec = _rec(kategoriler=["Kimlik"], amaclar=["x"], veri_turleri=["y"],
               hukuki_sebepler=["z"], saklama_sureleri=["1 yil"], aktarim=["Grup ici"])
    out = enrich_inventory([rec], "otel", repo)
    assert out == []


def test_canonicalizes_person_group_variants():
    from legal_core.canonical import load_canonicalizer
    canon = load_canonicalizer()
    repo = DictProcessRepository([_grounding(kisi_grubu="Aktif Çalışan", saklama_sureleri=["10 yil"])])
    rec = _rec(kisi_grubu="aktif çalişan", kategoriler=["Kimlik"], saklama_sureleri=[])
    out = enrich_inventory([rec], "otel", repo, canonicalizer=canon)
    assert out and out[0].oneriler.get("saklama_sureleri") == ["10 yil"]
