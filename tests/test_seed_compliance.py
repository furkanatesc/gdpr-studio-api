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


def test_module_requirements_is_empty_pending_t7():
    # T7 BLOKLU: içerik gelene dek boş kalmalı (uydurma yok).
    assert REQUIREMENTS == []
