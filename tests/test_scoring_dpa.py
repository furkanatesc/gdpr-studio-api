from legal_core.dpa_scope import DpaScope
from legal_core.scoring import dpa_completeness_score


def _scope(**kw):
    base = dict(eslesen_surecler=[], kategoriler=[], veri_turleri=[], amaclar=[],
                saklama_sureleri=[], teknik_tedbirler=[], idari_tedbirler=[])
    base.update(kw)
    return DpaScope(**base)


def test_empty_scope_none():
    assert dpa_completeness_score(_scope()) is None


def test_all_five_slots_filled():
    s = _scope(eslesen_surecler=["r"], kategoriler=["Kimlik"], amaclar=["A"],
               saklama_sureleri=["10 yıl"], teknik_tedbirler=["Şifreleme"])
    assert dpa_completeness_score(s) == 1.0


def test_partial():
    s = _scope(eslesen_surecler=["r"], veri_turleri=["Ad"], amaclar=[],
               saklama_sureleri=[], idari_tedbirler=["Politika"])
    # slotlar: (kat|veri)=1, amac=0, saklama=0, tedbir=1, surec>=1=1 -> 3/5
    assert dpa_completeness_score(s) == 0.6
