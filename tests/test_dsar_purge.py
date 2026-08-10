"""DSAR (H3-2 Part 2) — gecikmeli purge servisi + iç uç guard."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.dsar_purge import purge_expired_orgs
from app.models import (
    AuditLog,
    Client,
    ComplianceStatus,
    Membership,
    Organization,
    User,
)


def _fk_session():
    """FK-zorlamalı in-memory sqlite → org-satırı ON DELETE CASCADE (audit_logs) gerçekten koşar."""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _rec):  # noqa: ANN001
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def _seed_org(session, *, status, deleted_days_ago=None, name="Org", supabase="sup"):
    oid = uuid.uuid4()
    deleted_at = (
        None if deleted_days_ago is None
        else datetime.now(UTC) - timedelta(days=deleted_days_ago)
    )
    session.add(Organization(id=oid, name=name, status=status, deleted_at=deleted_at))
    u = User(supabase_user_id=supabase, email=f"{name}@x.io")
    session.add(u)
    session.flush()
    session.add(Membership(user_id=u.id, org_id=oid, role="yonetici"))
    session.add(Client(org_id=oid, name="C"))
    session.add(ComplianceStatus(org_id=oid, requirement_key="k", status="yapildi", source="user"))
    session.add(AuditLog(org_id=oid, action="x"))
    session.commit()
    return oid, u.id


def test_purge_deletes_expired_org_and_cascades_audit():
    s = _fk_session()
    oid, uid = _seed_org(s, status="deleting", deleted_days_ago=20, supabase="sup-1")
    calls: list[str] = []

    res = purge_expired_orgs(
        s, grace_days=14, supabase_delete=lambda sup: (calls.append(sup) or True)
    )

    assert res["count"] == 1
    assert s.get(Organization, oid) is None
    assert s.get(User, uid) is None
    for model in (Client, ComplianceStatus, AuditLog):
        assert s.scalar(select(func.count()).select_from(model).where(model.org_id == oid)) == 0
    assert calls == ["sup-1"]  # Supabase auth silme çağrıldı
    assert res["purged"][0]["supabaseDeleted"] == 1


def test_purge_skips_active_and_within_grace():
    s = _fk_session()
    a, _ = _seed_org(s, status="active", name="Aktif", supabase="a")
    b, _ = _seed_org(s, status="deleting", deleted_days_ago=5, name="Yeni", supabase="b")

    res = purge_expired_orgs(s, grace_days=14)

    assert res["count"] == 0
    assert s.get(Organization, a) is not None
    assert s.get(Organization, b) is not None  # grace penceresi dolmadı


def test_purge_idempotent():
    s = _fk_session()
    _seed_org(s, status="deleting", deleted_days_ago=20)
    assert purge_expired_orgs(s, grace_days=14)["count"] == 1
    assert purge_expired_orgs(s, grace_days=14)["count"] == 0


# --- iç uç guard (fail-closed) ---

def test_internal_purge_forbidden_without_token(client):
    r = client.post("/api/internal/purge")
    assert r.status_code == 403


def test_internal_purge_forbidden_wrong_token(client):
    r = client.post("/api/internal/purge", headers={"X-Internal-Token": "yanlis"})
    assert r.status_code == 403
