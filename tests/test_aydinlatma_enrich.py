from app.aydinlatma_enrich import EnrichedSection, enrich_sections
from legal_core.adapters import DictProcessRepository
from legal_core.aggregate_sections import Section
from legal_core.canonical import Canonicalizer
from legal_core.normalize import norm


def _process(sector="Perakende", kisi_grubu="Calisan", kategoriler=None, **data):
    return {
        "sector": sector,
        "kisi_grubu": kisi_grubu,
        "departman": "Insan Kaynaklari",
        "is_sureci": "Ise Giris Islemleri",
        "alt_surec": "Kimlik teyidi",
        "data": {
            "kategoriler": kategoriler if kategoriler is not None else ["Kimlik"],
            **data,
        },
    }


def test_enrich_suggests_grounding_value_for_empty_field():
    repo = DictProcessRepository(
        [
            _process(
                kategoriler=["Kimlik"],
                saklama_sureleri=["10 yil"],
            )
        ]
    )
    section = Section(
        is_sureci="Ise Giris Islemleri",
        kisi_gruplari=["Calisan"],
        kategoriler=["Kimlik"],
        saklama_sureleri=[],
    )

    result = enrich_sections([section], "Perakende", repo)

    assert len(result) == 1
    enriched = result[0]
    assert isinstance(enriched, EnrichedSection)
    assert enriched.saklama_sureleri == []
    assert enriched.oneriler["saklama_sureleri"] == ["10 yil"]


def test_enrich_no_key_when_no_grounding_match():
    repo = DictProcessRepository([])
    section = Section(
        is_sureci="Ise Giris Islemleri",
        kisi_gruplari=["Calisan"],
        saklama_sureleri=[],
    )

    result = enrich_sections([section], "Perakende", repo)

    assert "saklama_sureleri" not in result[0].oneriler


def test_enrich_does_not_suggest_for_filled_field():
    repo = DictProcessRepository(
        [_process(kategoriler=["Kimlik"], hukuki_sebepler=["Baska Sebep"])]
    )
    section = Section(
        is_sureci="Ise Giris Islemleri",
        kisi_gruplari=["Calisan"],
        kategoriler=["Kimlik"],
        hukuki_sebepler=["Mevcut Sebep"],
    )

    result = enrich_sections([section], "Perakende", repo)

    assert "hukuki_sebepler" not in result[0].oneriler
    assert result[0].hukuki_sebepler == ["Mevcut Sebep"]


def test_enrich_suggests_additive_amac_even_when_filled():
    """S2: amaclar DOLU olsa da grounding'den EK standart amac onerisi sunulur (additive;
    avukat: birden fazla oneri, ekle/cikar). Mevcut degerler oneriden cikarilir."""
    repo = DictProcessRepository(
        [_process(kategoriler=["Kimlik"], amaclar=["Ozluk dosyasi", "Saklama ve Arsiv"])]
    )
    section = Section(
        is_sureci="Ise Giris Islemleri",
        kisi_gruplari=["Calisan"],
        kategoriler=["Kimlik"],
        amaclar=["Ozluk dosyasi"],
    )

    result = enrich_sections([section], "Perakende", repo)

    assert result[0].amaclar == ["Ozluk dosyasi"]  # section degeri korunur
    assert result[0].oneriler["amaclar"] == ["Saklama ve Arsiv"]  # additive, mevcut haric


def test_enrich_never_suggests_aktarim_or_toplama():
    repo = DictProcessRepository(
        [_process(kategoriler=["Kimlik"], saklama_sureleri=["10 yil"])]
    )
    section = Section(
        is_sureci="Ise Giris Islemleri",
        kisi_gruplari=["Calisan"],
        kategoriler=["Kimlik"],
        aktarim=[],
        toplama=[],
    )

    result = enrich_sections([section], "Perakende", repo)

    assert "aktarim" not in result[0].oneriler
    assert "toplama" not in result[0].oneriler


def test_enrich_category_filter_excludes_unrelated_candidate():
    repo = DictProcessRepository(
        [
            _process(kategoriler=["Kimlik"], saklama_sureleri=["10 yil"]),
            _process(kategoriler=["Finans"], saklama_sureleri=["5 yil"]),
        ]
    )
    section = Section(
        is_sureci="Ise Giris Islemleri",
        kisi_gruplari=["Calisan"],
        kategoriler=["Kimlik"],
        saklama_sureleri=[],
    )

    result = enrich_sections([section], "Perakende", repo)

    assert result[0].oneriler["saklama_sureleri"] == ["10 yil"]


def test_enrich_merges_candidates_from_multiple_person_groups():
    repo = DictProcessRepository(
        [
            _process(kisi_grubu="Calisan", kategoriler=["Kimlik"], saklama_sureleri=["10 yil"]),
            _process(kisi_grubu="Calisan Adayi", kategoriler=["Kimlik"], saklama_sureleri=["2 yil"]),
        ]
    )
    section = Section(
        is_sureci="Ise Giris Islemleri",
        kisi_gruplari=["Calisan", "Calisan Adayi"],
        kategoriler=["Kimlik"],
        saklama_sureleri=[],
    )

    result = enrich_sections([section], "Perakende", repo)

    assert result[0].oneriler["saklama_sureleri"] == ["10 yil", "2 yil"]


def _canonicalizer(kisi_gruplari_canonical=None, kisi_gruplari_synonyms=None):
    return Canonicalizer(
        {
            "kisi_gruplari": {
                "canonical": kisi_gruplari_canonical or ["Calisan"],
                "synonyms": kisi_gruplari_synonyms or {},
            },
            "kategoriler": {"canonical": ["Kimlik", "Finans"], "synonyms": {}},
        }
    )


def test_enrich_canonicalizer_none_matches_current_behavior():
    repo = DictProcessRepository(
        [_process(kategoriler=["Kimlik"], saklama_sureleri=["10 yil"])]
    )
    section = Section(
        is_sureci="Ise Giris Islemleri",
        kisi_gruplari=["Calisan"],
        kategoriler=["Kimlik"],
        saklama_sureleri=[],
    )

    result = enrich_sections([section], "Perakende", repo, canonicalizer=None)

    assert result[0].oneriler["saklama_sureleri"] == ["10 yil"]


def test_enrich_canonicalizer_falls_back_to_loose_pool_when_precise_empty():
    repo = DictProcessRepository(
        [
            _process(
                kisi_grubu="Calisan",
                kategoriler=["Finans"],
                amaclar=["Bordro islemleri"],
                saklama_sureleri=["5 yil"],
            )
        ]
    )
    section = Section(
        is_sureci="Ise Giris Islemleri",
        kisi_gruplari=["Calisan"],
        kategoriler=["Kimlik"],
        amaclar=[],
        saklama_sureleri=[],
    )

    result = enrich_sections(
        [section], "Perakende", repo, canonicalizer=_canonicalizer()
    )

    assert result[0].oneriler["amaclar"] == ["Bordro islemleri"]
    assert result[0].oneriler["saklama_sureleri"] == ["5 yil"]


def test_enrich_canonicalizer_matches_synonym_person_group():
    repo = DictProcessRepository(
        [
            _process(
                kisi_grubu="Aktif Çalışan",
                kategoriler=["Kimlik"],
                saklama_sureleri=["3 yil"],
            )
        ]
    )
    section = Section(
        is_sureci="Ise Giris Islemleri",
        kisi_gruplari=["Calisan"],
        kategoriler=[],
        saklama_sureleri=[],
    )

    canonicalizer = _canonicalizer(
        kisi_gruplari_canonical=["Aktif Çalışan"],
        kisi_gruplari_synonyms={norm("Calisan"): "Aktif Çalışan"},
    )

    result_with = enrich_sections(
        [section], "Perakende", repo, canonicalizer=canonicalizer
    )
    result_without = enrich_sections([section], "Perakende", repo)

    assert result_with[0].oneriler["saklama_sureleri"] == ["3 yil"]
    assert "saklama_sureleri" not in result_without[0].oneriler


def test_enrich_canonicalizer_does_not_suggest_for_filled_field_or_aktarim_toplama():
    repo = DictProcessRepository(
        [
            _process(
                kategoriler=["Kimlik"],
                hukuki_sebepler=["Baska Sebep"],
                saklama_sureleri=["10 yil"],
            )
        ]
    )
    section = Section(
        is_sureci="Ise Giris Islemleri",
        kisi_gruplari=["Calisan"],
        kategoriler=["Kimlik"],
        hukuki_sebepler=["Mevcut Sebep"],
        aktarim=[],
        toplama=[],
    )

    result = enrich_sections(
        [section], "Perakende", repo, canonicalizer=_canonicalizer()
    )

    assert "hukuki_sebepler" not in result[0].oneriler
    assert result[0].hukuki_sebepler == ["Mevcut Sebep"]
    assert "aktarim" not in result[0].oneriler
    assert "toplama" not in result[0].oneriler
