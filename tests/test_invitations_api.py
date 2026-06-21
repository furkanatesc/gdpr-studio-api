"""Davet API uçları entegrasyon testleri (A9)."""

from __future__ import annotations


def test_admin_creates_and_lists_invitation(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    r = client_fresh.post("/api/invitations", json={"email": "yeni@b.com", "role": "avukat"})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "pending"
    lst = client_fresh.get("/api/invitations").json()
    assert len(lst) == 1 and lst[0]["email"] == "yeni@b.com"


def test_accept_invitation_creates_membership(client_fresh, accept_as):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    inv = client_fresh.post("/api/invitations", json={"email": "yeni@b.com", "role": "avukat"}).json()
    out = accept_as(sub="sb-2", email="yeni@b.com", token=inv["token"])
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


def test_email_mismatch_on_accept_returns_403(client_fresh, accept_as):
    """Token farklı e-posta için oluşturulmuş; yanlış e-posta ile kabul → 403."""
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    inv = client_fresh.post("/api/invitations", json={"email": "yeni@b.com", "role": "avukat"}).json()
    out = accept_as(sub="sb-3", email="baska@b.com", token=inv["token"])
    assert out.status_code == 403, out.text
