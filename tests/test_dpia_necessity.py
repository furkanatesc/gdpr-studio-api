from legal_core.dpia_necessity import DpiaAnket, evaluate_dpia_necessity
from legal_core.models import ProcessRecord


def _rec(**kw):
    base = dict(departman="IK", is_sureci="Ozluk", alt_surec="Bordro", kisi_grubu="Calisan")
    base.update(kw)
    return ProcessRecord(**base)


def _anket(**kw):
    base = dict(buyuk_olcek=False, yeni_teknoloji=False, savunmasiz_grup=False, veri_eslestirme=False)
    base.update(kw)
    return DpiaAnket(**base)


def test_ozel_nitelikli_auto_detected():
    v = evaluate_dpia_necessity([_rec(kategoriler=["Sağlık Bilgileri"])], _anket())
    assert v.ozel_nitelikli_var is True
    assert "ozel_nitelikli" in v.tetiklenenler


def test_profilleme_auto_detected_from_islem():
    v = evaluate_dpia_necessity([_rec(kategoriler=["Kimlik"], islem=["Profilleme ve skorlama"])], _anket())
    assert v.profilleme_var is True


def test_verdict_zorunlu_when_two_or_more():
    # ozel nitelikli (auto) + savunmasiz grup (anket) = 2 -> zorunlu
    v = evaluate_dpia_necessity([_rec(kategoriler=["Biyometrik Veri"])], _anket(savunmasiz_grup=True))
    assert v.kriter_sayisi == 2
    assert v.zorunlu is True


def test_verdict_not_zorunlu_when_one():
    v = evaluate_dpia_necessity([_rec(kategoriler=["Kimlik"])], _anket(yeni_teknoloji=True))
    assert v.kriter_sayisi == 1
    assert v.zorunlu is False
