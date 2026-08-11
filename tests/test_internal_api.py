import uuid

from sqlalchemy import select

from app.config import get_settings
from app.models import AuditLog, Organization


def _tok(monkeypatch):
    monkeypatch.setattr(get_settings(), "internal_api_token", "test-tok")
    return {"X-Internal-Token": "test-tok"}


def _seed_org(db_session, status="active"):
    oid = uuid.uuid4()
    db_session.add(Organization(id=oid, name="Op", status=status))
    db_session.commit()
    return oid


def test_suspend_sets_status_and_audit(client, db_session, monkeypatch):
    h = _tok(monkeypatch)
    oid = _seed_org(db_session)
    r = client.post(f"/api/internal/orgs/{oid}/suspend", headers=h)
    assert r.status_code == 200
    db_session.expire_all()
    assert db_session.get(Organization, oid).status == "suspended"
    actions = [a.action for a in db_session.scalars(select(AuditLog).where(AuditLog.org_id == oid))]
    assert "org.suspended" in actions


def test_reactivate_restores_active(client, db_session, monkeypatch):
    h = _tok(monkeypatch)
    oid = _seed_org(db_session, status="suspended")
    r = client.post(f"/api/internal/orgs/{oid}/reactivate", headers=h)
    assert r.status_code == 200
    db_session.expire_all()
    assert db_session.get(Organization, oid).status == "active"


def test_suspend_deleting_org_conflict(client, db_session, monkeypatch):
    h = _tok(monkeypatch)
    oid = _seed_org(db_session, status="deleting")
    r = client.post(f"/api/internal/orgs/{oid}/suspend", headers=h)
    assert r.status_code == 409


def test_reactivate_non_suspended_conflict(client, db_session, monkeypatch):
    h = _tok(monkeypatch)
    oid = _seed_org(db_session, status="active")
    r = client.post(f"/api/internal/orgs/{oid}/reactivate", headers=h)
    assert r.status_code == 409


def test_suspend_forbidden_without_token(client, db_session):
    oid = _seed_org(db_session)
    assert client.post(f"/api/internal/orgs/{oid}/suspend").status_code == 403
