from datetime import datetime

from legal_core.ihlal import IhlalOlay, evaluate_ihlal_bildirim


def _olay(**ov):
    base = dict(
        tespit=datetime(2026, 8, 5, 10, 0),
        tur="Yetkisiz erişim",
        etkilenen_kategoriler=["Kimlik"],
        ozel_nitelikli_secili=False,
        kimlik_finansal=False,
        sifreli=False,
        kisi_sayisi=10,
        nasil="test",
        onlemler="test",
    )
    base.update(ov)
    return IhlalOlay(**base)


def test_kurul_bildirimi_her_zaman_gerekli():
    v = evaluate_ihlal_bildirim(_olay(), simdi=datetime(2026, 8, 5, 12, 0))
    assert v.kurul_gerekli is True


def test_ozel_nitelikli_kategori_envanterden_tetikler():
    v = evaluate_ihlal_bildirim(
        _olay(etkilenen_kategoriler=["Sağlık Bilgileri"]),
        simdi=datetime(2026, 8, 5, 12, 0),
    )
    assert v.ozel_nitelikli_var is True
    assert v.ilgili_kisi_gerekli is True
    assert "ozel_nitelikli" in v.ilgili_kisi_sinyaller


def test_buyuk_olcek_tek_basina_tetikler():
    v = evaluate_ihlal_bildirim(_olay(kisi_sayisi=1500), simdi=datetime(2026, 8, 5, 12, 0))
    assert v.ilgili_kisi_gerekli is True
    assert "buyuk_olcek" in v.ilgili_kisi_sinyaller


def test_sifreli_muafiyet_ilgili_kisiyi_kaldirir():
    v = evaluate_ihlal_bildirim(
        _olay(sifreli=True, etkilenen_kategoriler=["Kimlik"], kimlik_finansal=False),
        simdi=datetime(2026, 8, 5, 12, 0),
    )
    assert v.ilgili_kisi_muafiyet is True
    assert v.ilgili_kisi_gerekli is False


def test_kimlik_finansal_sifreli_ise_muaf():
    v = evaluate_ihlal_bildirim(
        _olay(sifreli=True, kimlik_finansal=True), simdi=datetime(2026, 8, 5, 12, 0)
    )
    assert v.ilgili_kisi_gerekli is False


def test_72_saat_asildi():
    v = evaluate_ihlal_bildirim(
        _olay(tespit=datetime(2026, 8, 1, 10, 0)), simdi=datetime(2026, 8, 5, 12, 0)
    )
    assert v.sure_asildi is True
    assert v.saat_kalan < 0
