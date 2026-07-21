import unicodedata

from legal_core.aggregate_sections import Section, aggregate_sections
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
        _record(is_sureci="Ortak Surec", kisi_grubu="Calisan", kategoriler=["Kimlik"]),
        _record(is_sureci="Ortak Surec", kisi_grubu="Musteri", kategoriler=["Iletisim"]),
    ]

    result = aggregate_sections(records, ["Calisan", "Musteri"])

    assert len(result) == 1
    section = result[0]
    assert section.is_sureci == "Ortak Surec"
    assert section.kisi_gruplari == ["Calisan", "Musteri"]
    assert section.kategoriler == ["Kimlik", "Iletisim"]


def test_aggregate_sections_target_group_nfc_trim_no_casefold():
    decomposed_target = unicodedata.normalize("NFD", "Çalışan") + "  "
    records = [_record(kisi_grubu=unicodedata.normalize("NFC", "Çalışan"))]

    assert len(aggregate_sections(records, [decomposed_target])) == 1
    # case-folding uygulanmamali: farkli case eslesmemeli
    assert aggregate_sections(records, ["çalışan"]) == []
