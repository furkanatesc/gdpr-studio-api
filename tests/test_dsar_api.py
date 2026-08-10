"""DSAR (H3-2) — export + erase (soft-delete) + fail-closed erişim."""

import uuid

from app.auth.identity import Identity, get_current_identity
from app.main import app
from app.models import AuditLog, Client, ComplianceStatus, Organization

_ORG = uuid.UUID("00000000-0000-0000-0000-000000000002")  # _DEV_IDENTITY org


def _seed_org(db_session, name="Test Kurum"):
    db_session.add(Organization(id=_ORG, name=name))
    db_session.add(Client(org_id=_ORG, name="Müvekkil A"))
    db_session.add(ComplianceStatus(org_id=_ORG, requirement_key="k1", status="yapildi", source="user"))
    db_session.commit()


# --- export ---

def test_export_returns_all_sections(client, db_session):
    _seed_org(db_session)
    r = client.get("/api/dsar/export")
    assert r.status_code == 200
    assert 'attachment; filename="kvkk-export-' in r.headers["content-disposition"]
    body = r.json()
    assert body["organization"]["name"] == "Test Kurum"
    assert body["clients"][0]["name"] == "Müvekkil A"
    assert body["complianceStatus"][0]["requirement_key"] == "k1"
    for key in ["users", "memberships", "invitations", "clients", "clientDocuments",
                "clientProcessors", "complianceStatus", "generatedDocuments",
                "subscriptions", "usageCounters", "processes", "auditLogs"]:
        assert key in body


def test_export_writes_audit(client, db_session):
    _seed_org(db_session)
    r = client.get("/api/dsar/export")
    assert r.status_code == 200
    assert db_session.query(AuditLog).filter_by(action="dsar.export").count() == 1


def test_export_only_yonetici(client, db_session):
    _seed_org(db_session)
    app.dependency_overrides[get_current_identity] = lambda: Identity(
        user_id=_ORG, org_id=_ORG, role="avukat", email="a@b.io"
    )
    try:
        r = client.get("/api/dsar/export")
        assert r.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_identity, None)


# --- erase (soft-delete) ---

def test_erase_sets_status_and_audit(client, db_session):
    _seed_org(db_session)
    r = client.post("/api/dsar/erase", json={"confirm": "Test Kurum"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "deleting"
    org = db_session.get(Organization, _ORG)
    assert org.status == "deleting"
    assert org.deleted_at is not None
    row = db_session.query(AuditLog).filter_by(action="org.erasure_requested").one()
    assert row.org_id == _ORG
    assert row.target_type == "org"


def test_erase_confirm_mismatch_422(client, db_session):
    _seed_org(db_session)
    r = client.post("/api/dsar/erase", json={"confirm": "Yanlış Ad"})
    assert r.status_code == 422
    assert db_session.get(Organization, _ORG).status == "active"


# --- fail-closed (gerçek get_current_identity) ---

def test_erase_then_access_fail_closed(client_fresh):
    b = client_fresh.post("/api/auth/bootstrap", json={"orgName": "Kapatılacak"})
    assert b.status_code == 200, b.text
    # kapatmadan önce erişim var
    assert client_fresh.get("/api/auth/me").status_code == 200
    # kapat
    e = client_fresh.post("/api/dsar/erase", json={"confirm": "Kapatılacak"})
    assert e.status_code == 200, e.text
    # artık her authed uç 403 (fail-closed)
    me = client_fresh.get("/api/auth/me")
    assert me.status_code == 403
    assert "kapatıl" in me.json()["detail"].lower()
    exp = client_fresh.get("/api/dsar/export")
    assert exp.status_code == 403
