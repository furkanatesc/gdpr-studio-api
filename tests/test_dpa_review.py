from legal_core.dpa_review import DPA_CHECKLIST, ReviewItem


def test_checklist_has_expected_items():
    assert len(DPA_CHECKLIST) == 11
    assert all(isinstance(it, ReviewItem) for it in DPA_CHECKLIST)


def test_checklist_ids_unique_and_nonempty():
    ids = [it.id for it in DPA_CHECKLIST]
    assert len(ids) == len(set(ids))
    assert all(it.id and it.baslik and it.kvkk_ref and it.aranan for it in DPA_CHECKLIST)


def test_three_red_flags_present():
    flags = [it for it in DPA_CHECKLIST if it.kirmizi_bayrak]
    assert len(flags) == 3
    flag_ids = {it.id for it in flags}
    assert {"ihlal_bildirim", "sozlesme_sonu", "kendi_amaci"} <= flag_ids
