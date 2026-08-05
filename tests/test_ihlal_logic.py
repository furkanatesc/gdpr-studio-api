from datetime import datetime

from legal_core.generate import generate_ihlal_stream
from legal_core.ihlal import (
    IhlalOlay,
    build_ihlal_ilgili_kisi_prompt,
    build_ihlal_kurul_prompt,
    evaluate_ihlal_bildirim,
)
from legal_core.models import ClientProfile


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


def _prof():
    return ClientProfile(ad="furkan", unvan="Genel Şirket")


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


def test_kurul_prompt_zorunlu_basliklar():
    p = build_ihlal_kurul_prompt(
        _olay(), _prof(), ["Kimlik"], ["Ad"], ["1.Şifreleme"], ["kural1"]
    )
    assert "İHLALİN TARİHİ" in p.upper()
    assert "ETKİLENEN" in p.upper()
    assert "İRTİBAT" in p.upper()


def test_ilgili_kisi_prompt_sade_dil_basliklar():
    p = build_ihlal_ilgili_kisi_prompt(_olay(), _prof(), ["Kimlik"])
    assert "önlem" in p.lower()


class _FakeProvider:
    model = "claude-x"
    last_result = None

    def __init__(self, capture):
        self._capture = capture

    def stream(self, prompt, max_tokens):
        self._capture.append(prompt)
        yield "İhlal bildirim gövdesi..."


def test_generate_ihlal_kurul_prompt_kullanir():
    seen = []
    events = list(generate_ihlal_stream(
        _olay(), _prof(), ["Kimlik"], ["Ad"], ["1.Şifreleme"], ["kural1"],
        "kurul", provider=_FakeProvider(seen), max_tokens=8000,
    ))
    assert "İHLAL BİLDİRİM FORMU" in seen[0]
    assert events[-1][0] == "done"


def test_generate_ihlal_ilgili_kisi_prompt_kullanir():
    seen = []
    list(generate_ihlal_stream(
        _olay(), _prof(), ["Kimlik"], ["Ad"], [], [],
        "ilgili_kisi", provider=_FakeProvider(seen), max_tokens=8000,
    ))
    assert "SİZİN ALABİLECEĞİNİZ" in seen[0].upper()


def test_ihlal_score_dolu_olay_tam():
    from legal_core.scoring import ihlal_completeness_score
    s = ihlal_completeness_score(_olay(nasil="x", onlemler="y", kisi_sayisi=5))
    assert s == 1.0


def test_ihlal_score_bos_alanlar_dusuk():
    from legal_core.scoring import ihlal_completeness_score
    s = ihlal_completeness_score(_olay(tur="", nasil="", onlemler="", kisi_sayisi=0,
                                       etkilenen_kategoriler=[]))
    assert s < 0.5
