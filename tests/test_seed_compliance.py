"""compliance_requirements idempotent seed yükleyici."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import ComplianceRequirement
from app.seed_compliance import REQUIREMENTS, seed_compliance_requirements


def _session():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, expire_on_commit=False)()


_SAMPLE = [
    {
        "key": "k1", "title": "Kalem 1", "madde_ref": "KVKK m.10", "description": "d1",
        "group": "G1", "source_type": "manual", "auto_signal": None, "sort_order": 1,
    },
    {
        "key": "k2", "title": "Kalem 2", "madde_ref": "KVKK m.12", "description": "d2",
        "group": "G1", "source_type": "auto", "auto_signal": "doc_generated:aydinlatma", "sort_order": 2,
    },
]


def test_seed_inserts_rows_and_returns_count():
    s = _session()
    n = seed_compliance_requirements(s, _SAMPLE)
    s.commit()
    assert n == 2
    assert s.query(ComplianceRequirement).count() == 2


def test_seed_is_idempotent_no_duplicates():
    s = _session()
    seed_compliance_requirements(s, _SAMPLE)
    s.commit()
    n2 = seed_compliance_requirements(s, _SAMPLE)  # ikinci çağrı → delete+insert
    s.commit()
    assert n2 == 2
    assert s.query(ComplianceRequirement).count() == 2
    # anahtarlar korunur
    assert {r.key for r in s.query(ComplianceRequirement).all()} == {"k1", "k2"}


def test_seed_empty_list_yields_zero():
    s = _session()
    n = seed_compliance_requirements(s, [])
    s.commit()
    assert n == 0
    assert s.query(ComplianceRequirement).count() == 0


def test_seed_replaces_previous_content():
    s = _session()
    seed_compliance_requirements(s, _SAMPLE)
    s.commit()
    smaller = [_SAMPLE[0]]
    n = seed_compliance_requirements(s, smaller)
    s.commit()
    assert n == 1
    assert {r.key for r in s.query(ComplianceRequirement).all()} == {"k1"}


_VALID_DOC_TYPES = {"aydinlatma", "cerez", "kayit", "dpa", "dpia", "ihlal"}


def test_requirements_iyi_bicimli():
    assert len(REQUIREMENTS) >= 20, "uyum listesi dolu olmalı"
    keys = [r["key"] for r in REQUIREMENTS]
    assert len(keys) == len(set(keys)), "anahtarlar benzersiz olmalı"
    for r in REQUIREMENTS:
        assert set(r) == {"key", "title", "madde_ref", "description", "group",
                          "source_type", "auto_signal", "sort_order"}, f"{r['key']} şema hatalı"
        assert r["source_type"] in ("manual", "auto"), r["key"]
        assert r["title"] and r["madde_ref"] and r["description"] and r["group"], f"{r['key']} boş alan"


def test_auto_kalemler_gecerli_dokuman_sinyaline_bagli():
    """auto_signal 'doc_generated:<tür>' formatında ve tür gerçek bir doküman türü olmalı."""
    for r in REQUIREMENTS:
        if r["source_type"] == "auto":
            assert r["auto_signal"] and r["auto_signal"].startswith("doc_generated:"), r["key"]
            tur = r["auto_signal"].split(":", 1)[1]
            assert tur in _VALID_DOC_TYPES, f"{r['key']}: bilinmeyen doküman türü {tur}"
        else:
            assert r["auto_signal"] is None, f"{r['key']}: manual kalemde auto_signal olmamalı"
