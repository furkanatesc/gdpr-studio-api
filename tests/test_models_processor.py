from legal_core.models import ProcessorInfo


def test_processor_info_defaults():
    p = ProcessorInfo(ad="Bulut A.Ş.", unvan="Bulut Bilişim A.Ş.")
    assert p.ad == "Bulut A.Ş."
    assert p.unvan == "Bulut Bilişim A.Ş."
    assert p.adres is None
    assert p.yurt_disi is False
    assert p.alt_isleyen_var is False
    assert p.aktarim_aliases == []


def test_processor_info_full():
    p = ProcessorInfo(
        ad="X", unvan="X Ltd", adres="İstanbul", yetkili_kisi="Ali",
        iletisim="a@x.co", vergi_dairesi_no="123", yurt_disi=True,
        alt_isleyen_var=True, aktarim_aliases=["Yurt Dışı Sunucu"],
    )
    assert p.yurt_disi is True
    assert p.aktarim_aliases == ["Yurt Dışı Sunucu"]
