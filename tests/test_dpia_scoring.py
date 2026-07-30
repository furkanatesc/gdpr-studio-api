from legal_core.models import ProcessRecord
from legal_core.scoring import dpia_completeness_score


def _rec(**kw):
    base = dict(departman="IK", is_sureci="Ozluk", alt_surec="Bordro", kisi_grubu="Calisan")
    base.update(kw)
    return ProcessRecord(**base)


def test_dpia_score_none_for_empty():
    assert dpia_completeness_score([]) is None


def test_dpia_score_counts_five_slots_incl_measures():
    r = _rec(kategoriler=["Kimlik"], amaclar=["x"], hukuki_sebepler=["y"],
             saklama_sureleri=["1 yil"], idari_tedbirler=["Erisim kontrolu"])
    assert dpia_completeness_score([r]) == 1.0


def test_dpia_score_measure_slot_from_either_field():
    r = _rec(kategoriler=["Kimlik"], amaclar=["x"], hukuki_sebepler=["y"],
             saklama_sureleri=["1 yil"], teknik_tedbirler=["Sifreleme"])
    assert dpia_completeness_score([r]) == 1.0  # teknik VEYA idari sayar
    r2 = _rec(kategoriler=["Kimlik"], amaclar=["x"], hukuki_sebepler=["y"], saklama_sureleri=["1 yil"])
    assert dpia_completeness_score([r2]) == 0.8  # tedbir slotu bos -> 4/5
