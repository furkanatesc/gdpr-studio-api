"""ComplianceRepository + GeneratedDocumentRepository — CRUD + org kapsamı (SQLite)."""

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import ComplianceRequirement, Organization
from app.repositories import ComplianceRepository, GeneratedDocumentRepository


def _session():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, expire_on_commit=False)()


def _org(s) -> uuid.UUID:
    org = Organization(name="Acme")
    s.add(org)
    s.flush()
    return org.id


def test_all_requirements_ordered_by_sort_order():
    s = _session()
    s.add(ComplianceRequirement(key="b", title="B", sort_order=2))
    s.add(ComplianceRequirement(key="a", title="A", sort_order=1))
    s.commit()
    repo = ComplianceRepository(s)
    keys = [r.key for r in repo.all_requirements()]
    assert keys == ["a", "b"]


def test_statuses_for_org_returns_dict_keyed_by_requirement_key():
    s = _session()
    org = _org(s)
    repo = ComplianceRepository(s)
    repo.upsert_status(org, "k1", "yapildi", "user", None, None)
    repo.upsert_status(org, "k2", "eksik", "user", "not-x", None)
    s.commit()
    d = repo.statuses_for_org(org)
    assert set(d) == {"k1", "k2"}
    assert d["k1"].status == "yapildi"
    assert d["k2"].note == "not-x"


def test_upsert_status_updates_existing_row_not_insert():
    s = _session()
    org = _org(s)
    repo = ComplianceRepository(s)
    first = repo.upsert_status(org, "k", "eksik", "user", None, None)
    s.commit()
    second = repo.upsert_status(org, "k", "yapildi", "user", "kanit", None)
    s.commit()
    assert first.id == second.id  # UPDATE, yeni satır değil
    d = repo.statuses_for_org(org)
    assert len(d) == 1
    assert d["k"].status == "yapildi"
    assert d["k"].note == "kanit"


def test_upsert_status_is_org_scoped():
    s = _session()
    org_a, org_b = _org(s), _org(s)
    repo = ComplianceRepository(s)
    repo.upsert_status(org_a, "k", "yapildi", "user", None, None)
    repo.upsert_status(org_b, "k", "eksik", "user", None, None)
    s.commit()
    assert repo.statuses_for_org(org_a)["k"].status == "yapildi"
    assert repo.statuses_for_org(org_b)["k"].status == "eksik"


def test_generated_document_record_and_doc_types_for_org():
    s = _session()
    org = _org(s)
    gdocs = GeneratedDocumentRepository(s)
    gdocs.record(org, "aydinlatma")
    gdocs.record(org, "cerez")
    gdocs.record(org, "aydinlatma")  # tekrar → set tekilleştirir
    s.commit()
    assert gdocs.doc_types_for_org(org) == {"aydinlatma", "cerez"}


def test_doc_types_for_org_is_org_scoped():
    s = _session()
    org_a, org_b = _org(s), _org(s)
    gdocs = GeneratedDocumentRepository(s)
    gdocs.record(org_a, "aydinlatma")
    gdocs.record(org_b, "cerez")
    s.commit()
    assert gdocs.doc_types_for_org(org_a) == {"aydinlatma"}
    assert gdocs.doc_types_for_org(org_b) == {"cerez"}
