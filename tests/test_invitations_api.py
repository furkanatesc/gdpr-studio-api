"""Davet API uçları entegrasyon testleri (A9)."""

from __future__ import annotations

from app.models import AuditLog


def test_admin_creates_and_lists_invitation(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    r = client_fresh.post("/api/invitations", json={"email": "yeni@b.com", "role": "avukat"})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending"
    lst = client_fresh.get("/api/invitations").json()
    assert len(lst) == 1 and lst[0]["email"] == "yeni@b.com"


def test_create_invitation_writes_audit_without_email(client_fresh, db_session):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    inv = client_fresh.post("/api/invitations", json={"email": "yeni@b.com", "role": "avukat"}).json()

    row = db_session.query(AuditLog).filter_by(action="invite.sent").one()
    assert row.target_type == "invite"
    assert row.target_id == inv["id"]
    assert row.meta == {"role": "avukat"}
    assert "yeni@b.com" not in (row.meta or {}).values()


def test_create_invitation_invalid_role_writes_no_audit(client_fresh, db_session):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    r = client_fresh.post("/api/invitations", json={"email": "yeni@b.com", "role": "hacker"})
    assert r.status_code == 422, r.text
    assert db_session.query(AuditLog).count() == 0


def test_revoke_invitation_writes_audit(client_fresh, db_session):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    inv = client_fresh.post("/api/invitations", json={"email": "yeni@b.com", "role": "avukat"}).json()
    r = client_fresh.delete(f"/api/invitations/{inv['id']}")
    assert r.status_code == 204, r.text

    row = db_session.query(AuditLog).filter_by(action="invite.revoked").one()
    assert row.target_type == "invite"
    assert row.target_id == inv["id"]


def test_accept_invitation_writes_audit(client_fresh, accept_as, create_invite, db_session):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    inv, token = create_invite("yeni@b.com", "avukat")
    out = accept_as(sub="sb-2", email="yeni@b.com", token=token)
    assert out.status_code == 200, out.text

    row = db_session.query(AuditLog).filter_by(action="invite.accepted").one()
    assert row.target_type == "invite"
    assert row.target_id == inv["id"]
    assert str(row.actor_user_id) == out.json()["userId"]


def test_accept_invitation_creates_membership(client_fresh, accept_as, create_invite):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    inv, token = create_invite("yeni@b.com", "avukat")
    out = accept_as(sub="sb-2", email="yeni@b.com", token=token)
    assert out.status_code == 200, out.text
    assert out.json()["role"] == "avukat"


def test_create_invitation_rejects_invalid_role(client):
    """Geçersiz rol değeri ile davet isteği → 422."""
    # client fixture: identity override var (yonetici) AMA org DB'de yok; endpoint
    # get_current_identity yerine require_role("yonetici") kullanır. Dependency
    # overrides get_current_identity'yi döndürür, dolayısıyla role guard geçer.
    # Rol geçersiz → 422.
    r = client.post("/api/invitations", json={"email": "x@b.com", "role": "hacker"})
    assert r.status_code == 422, r.text


def test_avukat_cannot_create_invitation(client_fresh):
    """avukat rolüyle davet oluşturma isteği → 403 (rol kapısı)."""
    import uuid

    from app.auth.identity import Identity, get_current_identity
    from app.main import app

    app.dependency_overrides[get_current_identity] = lambda: Identity(
        user_id=uuid.uuid4(), org_id=uuid.uuid4(), role="avukat", email="avukat@b.com"
    )
    try:
        r = client_fresh.post("/api/invitations", json={"email": "x@y.com", "role": "avukat"})
        assert r.status_code == 403, r.text
    finally:
        app.dependency_overrides.pop(get_current_identity, None)


def test_email_mismatch_on_accept_returns_403(client_fresh, accept_as, create_invite):
    """Token farklı e-posta için oluşturulmuş; yanlış e-posta ile kabul → 403."""
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    inv, token = create_invite("yeni@b.com", "avukat")
    out = accept_as(sub="sb-3", email="baska@b.com", token=token)
    assert out.status_code == 403, out.text
