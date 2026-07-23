from app.modules.compliance_logic import DOC_TYPE_COMPLIANCE_KEYS, compliance_snapshot_score


def test_snapshot_aydinlatma_keys_defined():
    keys = DOC_TYPE_COMPLIANCE_KEYS["aydinlatma"]
    assert "aydinlatma_metni" in keys and "haklar_karsilanmasi" in keys


def test_snapshot_all_done_is_one():
    statuses = {k: "yapildi" for k in DOC_TYPE_COMPLIANCE_KEYS["aydinlatma"]}
    assert compliance_snapshot_score(statuses, "aydinlatma") == 1.0


def test_snapshot_missing_key_counts_as_not_done():
    # hic statu yok -> yapildi 0 / applicable = tum keyler -> 0.0
    assert compliance_snapshot_score({}, "aydinlatma") == 0.0


def test_snapshot_uygulanmaz_drops_from_denominator():
    keys = DOC_TYPE_COMPLIANCE_KEYS["aydinlatma"]  # 6 madde
    statuses = {keys[0]: "yapildi", keys[1]: "uygulanmaz"}
    # yapildi=1, uygulanmaz=1, total=6 -> 1/(6-1)=0.2
    assert compliance_snapshot_score(statuses, "aydinlatma") == 0.2


def test_snapshot_unknown_doctype_is_none():
    assert compliance_snapshot_score({}, "bilinmeyen") is None


def test_snapshot_all_uygulanmaz_is_none():
    statuses = {k: "uygulanmaz" for k in DOC_TYPE_COMPLIANCE_KEYS["dpa"]}
    assert compliance_snapshot_score(statuses, "dpa") is None  # payda 0
