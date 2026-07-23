import unicodedata

from legal_core.aggregate_sections import Section, aggregate_sections
from legal_core.canonical import Canonicalizer
from legal_core.models import ProcessRecord


def _record(**overrides):
    base = dict(
        departman="Insan Kaynaklari",
        is_sureci="Ise Giris Islemleri",
        alt_surec="Kimlik teyidi",
        kisi_grubu="Calisan",
        kategoriler=["Kimlik"],
        veri_turleri=["Ad, Soyad"],
        amaclar=["Ozluk dosyasi olusturma"],
        hukuki_sebepler=["5/2c Hukuki Yukumluluk"],
        dayanaklar=["4857 s. Kanun"],
        saklama_sureleri=["10 yil"],
        islem=["Kaydetme"],
        ortam_format=["Elektronik"],
        konum=["Sunucu"],
        idari_tedbirler=["Erisim yetkilendirme"],
        teknik_tedbirler=["Sifreleme"],
    )
    base.update(overrides)
    return ProcessRecord(**base)


def test_aggregate_sections_filters_groups_and_merges():
    records = [
        _record(
            is_sureci="Ise Giris Islemleri",
            kisi_grubu="Calisan",
            kategoriler=["Kimlik"],
            veri_turleri=["Ad, Soyad"],
            amaclar=["Ozluk dosyasi olusturma"],
            hukuki_sebepler=["5/2c Hukuki Yukumluluk"],
            saklama_sureleri=["10 yil"],
        ),
        _record(
            is_sureci="Ise Giris Islemleri",
            kisi_grubu="Calisan Adayi",
            kategoriler=["Kimlik", "Iletisim"],
            veri_turleri=["Ad, Soyad", "Telefon"],
            amaclar=["Ozluk dosyasi olusturma", "Ise alim degerlendirmesi"],
            hukuki_sebepler=["5/2c Hukuki Yukumluluk"],
            saklama_sureleri=["10 yil", "2 yil"],
        ),
        _record(
            is_sureci="Bordro Islemleri",
            alt_surec="Ucret hesaplama",
            kisi_grubu="Calisan",
            kategoriler=["Finans"],
            veri_turleri=["Maas"],
            amaclar=["Ucret odemesi"],
            hukuki_sebepler=["5/2c Hukuki Yukumluluk"],
            saklama_sureleri=["10 yil"],
        ),
        _record(
            is_sureci="Ziyaretci Kayit",
            kisi_grubu="Ziyaretci",
            kategoriler=["Kimlik"],
            veri_turleri=["Ad, Soyad"],
            amaclar=["Guvenlik"],
            hukuki_sebepler=["Mesru menfaat"],
            saklama_sureleri=["1 yil"],
        ),
    ]

    result = aggregate_sections(records, ["Calisan", "Calisan Adayi"])

    # 2 distinct is_sureci (Ise Giris + Bordro) -> is_sureci'ye gore gruplanir (alt_surec'e
    # bolunmez); etiket = is_sureci.
    assert [s.is_sureci for s in result] == ["Ise Giris Islemleri", "Bordro Islemleri"]

    first = result[0]
    assert isinstance(first, Section)
    assert first.kisi_gruplari == ["Calisan", "Calisan Adayi"]
    assert first.kategoriler == ["Kimlik", "Iletisim"]
    assert first.veri_turleri == ["Ad, Soyad", "Telefon"]
    assert first.amaclar == ["Ozluk dosyasi olusturma", "Ise alim degerlendirmesi"]
    assert first.hukuki_sebepler == ["5/2c Hukuki Yukumluluk"]
    assert first.saklama_sureleri == ["10 yil", "2 yil"]
    assert first.aktarim == []
    assert first.toplama == []

    second = result[1]
    assert second.is_sureci == "Bordro Islemleri"
    assert second.kisi_gruplari == ["Calisan"]
    assert second.kategoriler == ["Finans"]


def test_aggregate_sections_section_carries_departman():
    """S4: Section, grup kayitlarinin departmanlarini tasir (enrich'in hukuk kuralina girdi)."""
    records = [
        _record(is_sureci="Sozlesme Yonetimi", departman="Hukuk", kisi_grubu="Calisan"),
        _record(is_sureci="Sozlesme Yonetimi", departman="Hukuk Isleri", kisi_grubu="Calisan Adayi"),
    ]
    result = aggregate_sections(records, ["Calisan", "Calisan Adayi"])
    assert len(result) == 1
    assert result[0].departman == ["Hukuk", "Hukuk Isleri"]


def test_aggregate_sections_splits_by_alt_surec_when_single_is_sureci():
    """Akilli gruplama: hedef grup TEK is_sureci'ye sahipse (PROGSA gibi jenerik
    "Uyelik Islemleri") alt_surec'e bolunur, etiket = alt_surec."""
    records = [
        _record(is_sureci="Uyelik Islemleri", alt_surec="Uye Kayitlari", kisi_grubu="Uye",
                kategoriler=["Kimlik"], amaclar=["Sozlesme"]),
        _record(is_sureci="Uyelik Islemleri", alt_surec="Odeme Alinmasi", kisi_grubu="Uye",
                kategoriler=["Finans"], amaclar=["Tahsilat"]),
    ]
    result = aggregate_sections(records, ["Uye"])
    assert [s.is_sureci for s in result] == ["Uye Kayitlari", "Odeme Alinmasi"]
    assert result[0].kategoriler == ["Kimlik"]
    assert result[1].kategoriler == ["Finans"]


def test_aggregate_sections_groups_by_is_sureci_when_multiple_is_sureci():
    """Akilli gruplama: birden fazla is_sureci varsa alt_surec'e BOLUNMEZ (belge patlamaz).
    Her is_sureci tek bolum; ayni is_sureci altindaki farkli alt_surec'ler birlesir."""
    records = [
        _record(is_sureci="Ise Alim", alt_surec="Basvuru", kisi_grubu="Calisan", kategoriler=["Kimlik"]),
        _record(is_sureci="Ise Alim", alt_surec="Mulakat", kisi_grubu="Calisan", kategoriler=["Iletisim"]),
        _record(is_sureci="Bordro", alt_surec="Maas Hesabi", kisi_grubu="Calisan", kategoriler=["Finans"]),
        _record(is_sureci="Bordro", alt_surec="Odeme", kisi_grubu="Calisan", kategoriler=["Finans"]),
    ]
    result = aggregate_sections(records, ["Calisan"])
    # 2 distinct is_sureci -> 2 bolum (4 alt_surec'e patlamaz), etiket = is_sureci
    assert [s.is_sureci for s in result] == ["Ise Alim", "Bordro"]
    assert result[0].kategoriler == ["Kimlik", "Iletisim"]


def test_aggregate_sections_label_falls_back_to_is_sureci_when_alt_empty():
    records = [
        _record(is_sureci="Ortak Surec", alt_surec="", kisi_grubu="Calisan", kategoriler=["Kimlik"]),
        _record(is_sureci="Ortak Surec", alt_surec="", kisi_grubu="Musteri", kategoriler=["Iletisim"]),
    ]
    result = aggregate_sections(records, ["Calisan", "Musteri"])
    assert len(result) == 1
    assert result[0].is_sureci == "Ortak Surec"


def test_aggregate_sections_merges_dedup_aktarim_toplama_from_records():
    records = [
        _record(
            is_sureci="Ise Giris Islemleri",
            kisi_grubu="Calisan",
            aktarim=["SGK", "Elektronik"],
            toplama=["Ilgili kisinin kendisi"],
        ),
        _record(
            is_sureci="Ise Giris Islemleri",
            kisi_grubu="Calisan Adayi",
            aktarim=["Elektronik", "Yurt disina aktarim"],
            toplama=["Ilgili kisinin kendisi", "Ucuncu taraf"],
        ),
    ]

    result = aggregate_sections(records, ["Calisan", "Calisan Adayi"])

    assert len(result) == 1
    assert result[0].aktarim == ["SGK", "Elektronik", "Yurt disina aktarim"]
    assert result[0].toplama == ["Ilgili kisinin kendisi", "Ucuncu taraf"]


def test_aggregate_sections_canonicalizes_kisi_grubu_display():
    """S5a: gorunen kisi grubu standart ada cevrilir (avukat: 'cevrilsin'). A-listesi
    synonym'i kisi_gruplari.json'da; canonicalizer ile display kanoniklesir."""
    from legal_core.canonical import load_canonicalizer
    canon = load_canonicalizer()
    records = [_record(kisi_grubu="Tedarikçi Yetkilisi")]
    result = aggregate_sections(records, ["Tedarikçi Yetkilisi"], canonicalizer=canon)
    assert result[0].kisi_gruplari == ["İş Ortağı / Tedarikçi Yetkilisi"]


def test_aggregate_sections_calisan_kisi_grubu_stays_raw():
    """S5a: 'Çalışan' synonym'i YOK (avukat: hepsi ayni kalmali) -> ham kalir."""
    from legal_core.canonical import load_canonicalizer
    canon = load_canonicalizer()
    records = [_record(kisi_grubu="Çalışan")]
    result = aggregate_sections(records, ["Çalışan"], canonicalizer=canon)
    assert result[0].kisi_gruplari == ["Çalışan"]


def test_aggregate_sections_empty_when_no_matching_group():
    records = [_record(kisi_grubu="Calisan")]
    assert aggregate_sections(records, ["Ziyaretci"]) == []


def test_aggregate_sections_empty_records_list():
    assert aggregate_sections([], ["Calisan"]) == []


def test_aggregate_sections_nfc_dedup_and_order():
    composed = unicodedata.normalize("NFC", "Çalışan Kayıtları")
    decomposed = unicodedata.normalize("NFD", "Çalışan Kayıtları")

    records = [
        _record(
            is_sureci="Sureç A",
            kisi_grubu="Calisan",
            kategoriler=[composed, "Kimlik"],
        ),
        _record(
            is_sureci="Sureç A",
            kisi_grubu="Calisan",
            kategoriler=[decomposed, "Kimlik", "  "],
        ),
    ]

    result = aggregate_sections(records, ["Calisan"])

    assert len(result) == 1
    assert result[0].kategoriler == [composed, "Kimlik"]


def test_aggregate_sections_merges_multiple_person_groups_into_one_section():
    records = [
        _record(is_sureci="Ortak Surec", alt_surec="Ortak Alt", kisi_grubu="Calisan", kategoriler=["Kimlik"]),
        _record(is_sureci="Ortak Surec", alt_surec="Ortak Alt", kisi_grubu="Musteri", kategoriler=["Iletisim"]),
    ]

    result = aggregate_sections(records, ["Calisan", "Musteri"])

    assert len(result) == 1
    section = result[0]
    assert section.is_sureci == "Ortak Alt"
    assert section.kisi_gruplari == ["Calisan", "Musteri"]
    assert section.kategoriler == ["Kimlik", "Iletisim"]


def test_aggregate_sections_target_group_nfc_trim_no_casefold():
    decomposed_target = unicodedata.normalize("NFD", "Çalışan") + "  "
    records = [_record(kisi_grubu=unicodedata.normalize("NFC", "Çalışan"))]

    assert len(aggregate_sections(records, [decomposed_target])) == 1
    # case-folding uygulanmamali: farkli case eslesmemeli
    assert aggregate_sections(records, ["çalışan"]) == []


def _canonicalizer():
    return Canonicalizer(
        {
            "veri_turleri": {"canonical": ["Ad-soyad"], "synonyms": {}},
            "kategoriler": {"canonical": ["Kimlik Bilgisi"], "synonyms": {}},
        }
    )


def test_aggregate_sections_with_canonicalizer_canonicalizes_output():
    records = [
        _record(
            is_sureci="Ise Giris Islemleri",
            kisi_grubu="Calisan",
            kategoriler=["Kimlik Bilgisi"],
            veri_turleri=["AD-SOYAD"],
        ),
        _record(
            is_sureci="Ise Giris Islemleri",
            kisi_grubu="Calisan",
            kategoriler=["kimlik bilgisi"],
            veri_turleri=["ad-soyad"],
        ),
    ]

    result = aggregate_sections(records, ["Calisan"], canonicalizer=_canonicalizer())

    assert len(result) == 1
    assert result[0].veri_turleri == ["Ad-soyad"]
    assert result[0].kategoriler == ["Kimlik Bilgisi"]


def test_aggregate_sections_without_canonicalizer_keeps_raw_values():
    records = [
        _record(
            is_sureci="Ise Giris Islemleri",
            kisi_grubu="Calisan",
            kategoriler=["Kimlik Bilgisi"],
            veri_turleri=["AD-SOYAD"],
        ),
    ]

    result = aggregate_sections(records, ["Calisan"])

    assert result[0].veri_turleri == ["AD-SOYAD"]
    assert result[0].kategoriler == ["Kimlik Bilgisi"]


def test_aggregate_sections_with_canonicalizer_unknown_value_stays_raw():
    records = [
        _record(
            is_sureci="Ise Giris Islemleri",
            kisi_grubu="Calisan",
            kategoriler=["Kimlik Bilgisi"],
            veri_turleri=["Bilinmeyen Deger XYZ"],
        ),
    ]

    result = aggregate_sections(records, ["Calisan"], canonicalizer=_canonicalizer())

    assert result[0].veri_turleri == ["Bilinmeyen Deger XYZ"]
