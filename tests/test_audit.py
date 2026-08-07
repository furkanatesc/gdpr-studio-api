import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base

ORG = uuid.UUID("00000000-0000-0000-0000-000000000002")
USER = uuid.UUID("00000000-0000-0000-0000-000000000003")


@pytest.fixture()
def session():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def test_get_client_ip_reads_contextvar():
    from app import observability

    token = observability._client_ip.set("203.0.113.5")
    try:
        assert observability.get_client_ip() == "203.0.113.5"
    finally:
        observability._client_ip.reset(token)


def test_get_client_ip_none_by_default():
    from app import observability

    assert observability.get_client_ip() is None


def test_record_audit_writes_fields(session):
    from app import observability
    from app.audit import record_audit
    from app.models import AuditLog

    rid = observability._request_id.set("req-123")
    ip = observability._client_ip.set("203.0.113.5")
    try:
        record_audit(session, org_id=ORG, action="membership.role_changed",
                     actor_user_id=USER, target_type="membership", target_id=str(USER),
                     meta={"from": "avukat", "to": "yonetici"})
        session.flush()
    finally:
        observability._request_id.reset(rid)
        observability._client_ip.reset(ip)

    row = session.query(AuditLog).one()
    assert row.action == "membership.role_changed"
    assert row.ip == "203.0.113.5" and row.request_id == "req-123"
    assert row.meta == {"from": "avukat", "to": "yonetici"}
    assert row.actor_user_id == USER and row.org_id == ORG


def test_record_audit_meta_none_ok(session):
    from app.audit import record_audit
    record_audit(session, org_id=ORG, action="invite.revoked", target_type="invite", target_id="x")
    session.flush()  # patlamaz
