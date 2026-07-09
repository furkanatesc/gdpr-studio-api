"""ORM model testleri — compliance tabloları (in-memory SQLite, CHECK ihlali)."""

import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    ComplianceRequirement,
    ComplianceStatus,
    GeneratedDocument,
    Organization,
)


def _session():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, expire_on_commit=False)()


def test_compliance_tables_registered():
    names = set(Base.metadata.tables)
    assert {"compliance_requirements", "compliance_status", "generated_documents"} <= names


def test_create_and_read_requirement():
    s = _session()
    req = ComplianceRequirement(
        key="aydinlatma_yukumlulugu",
        title="Aydınlatma Yükümlülüğü",
        madde_ref="KVKK m.10",
        description="Veri sorumlusu aydınlatma yapmalı.",
        group="Belgelendirme",
        source_type="auto",
        auto_signal="doc_generated:aydinlatma",
        sort_order=1,
    )
    s.add(req)
    s.commit()
    got = s.query(ComplianceRequirement).filter_by(key="aydinlatma_yukumlulugu").one()
    assert got.title == "Aydınlatma Yükümlülüğü"
    assert got.source_type == "auto"
    assert got.auto_signal == "doc_generated:aydinlatma"


def test_create_and_read_status_and_generated_document():
    s = _session()
    org = Organization(name="Acme")
    s.add(org)
    s.flush()
    st = ComplianceStatus(
        org_id=org.id, requirement_key="aydinlatma_yukumlulugu", status="yapildi", source="user"
    )
    doc = GeneratedDocument(org_id=org.id, doc_type="aydinlatma")
    s.add_all([st, doc])
    s.commit()
    assert s.query(ComplianceStatus).filter_by(org_id=org.id).one().status == "yapildi"
    assert s.query(GeneratedDocument).filter_by(org_id=org.id).one().doc_type == "aydinlatma"


def test_status_check_constraint_rejects_invalid_status():
    s = _session()
    org = Organization(name="Acme")
    s.add(org)
    s.flush()
    s.add(ComplianceStatus(org_id=org.id, requirement_key="k", status="gecersiz", source="user"))
    with pytest.raises(IntegrityError):
        s.commit()


def test_generated_document_check_constraint_rejects_invalid_type():
    s = _session()
    org = Organization(name="Acme")
    s.add(org)
    s.flush()
    s.add(GeneratedDocument(org_id=org.id, doc_type="gecersiz"))
    with pytest.raises(IntegrityError):
        s.commit()


def test_status_unique_org_key_constraint():
    s = _session()
    org = Organization(name="Acme")
    s.add(org)
    s.flush()
    s.add(ComplianceStatus(org_id=org.id, requirement_key="k", status="eksik", source="user"))
    s.commit()
    s.add(ComplianceStatus(org_id=org.id, requirement_key="k", status="yapildi", source="user"))
    with pytest.raises(IntegrityError):
        s.commit()
    s.rollback()
    # Aynı key farklı org → OK
    other = Organization(name="Other")
    s.add(other)
    s.flush()
    s.add(ComplianceStatus(org_id=other.id, requirement_key="k", status="eksik", source="user"))
    s.commit()
    assert s.query(ComplianceStatus).filter_by(requirement_key="k").count() == 2


def test_requirement_source_type_check():
    s = _session()
    s.add(ComplianceRequirement(key="x", title="X", source_type="bogus"))
    with pytest.raises(IntegrityError):
        s.commit()


def test_status_requires_valid_source():
    s = _session()
    org = Organization(name="Acme")
    s.add(org)
    s.flush()
    s.add(ComplianceStatus(org_id=org.id, requirement_key="k", status="eksik", source="bogus"))
    with pytest.raises(IntegrityError):
        s.commit()


def test_generated_document_id_is_uuid():
    s = _session()
    org = Organization(name="Acme")
    s.add(org)
    s.flush()
    doc = GeneratedDocument(org_id=org.id, doc_type="cerez")
    s.add(doc)
    s.commit()
    assert isinstance(doc.id, uuid.UUID)
