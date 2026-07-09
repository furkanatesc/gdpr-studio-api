"""Uyum skoru + otomatik sinyal saf mantığı (DB'siz)."""

from app.modules.compliance_logic import compute_score, evaluate_auto_signal


def test_compute_score_excludes_uygulanmaz_from_denominator():
    # 3 yapildi / (10 toplam - 2 uygulanmaz) = 3/8
    assert compute_score(3, 10, 2) == 0.375


def test_compute_score_all_uygulanmaz_is_none():
    assert compute_score(0, 5, 5) is None


def test_compute_score_empty_is_none():
    assert compute_score(0, 0, 0) is None


def test_compute_score_denominator_negative_is_none():
    # savunmacı: uygulanmaz > total olamaz ama payda <= 0 → None
    assert compute_score(0, 2, 3) is None


def test_compute_score_full():
    assert compute_score(4, 4, 0) == 1.0


def test_evaluate_auto_signal_doc_generated_present_yapildi():
    assert evaluate_auto_signal("doc_generated:aydinlatma", {"aydinlatma"}) == "yapildi"


def test_evaluate_auto_signal_doc_generated_absent_eksik():
    assert evaluate_auto_signal("doc_generated:aydinlatma", set()) == "eksik"


def test_evaluate_auto_signal_doc_generated_other_types_eksik():
    assert evaluate_auto_signal("doc_generated:dpia", {"aydinlatma", "cerez"}) == "eksik"


def test_evaluate_auto_signal_unknown_source_is_none():
    assert evaluate_auto_signal("inventory_nonempty", {"aydinlatma"}) is None
    assert evaluate_auto_signal("", set()) is None
