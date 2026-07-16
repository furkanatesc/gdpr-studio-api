"""Üye yönetimi API — H2 (mimari review: offboarding + üye listeleme/rol yoktu).

client_fresh dev-bypass ile kimliği DB'den çözer → bootstrap (dev-user=yönetici) + davet+kabul
(sb-2=avukat) gerçek 2 üyeli org kurar. İstekler dev-user (yönetici) olarak koşar.
"""

from __future__ import annotations

import uuid

from app.auth.identity import Identity, get_current_identity
from app.main import app


def _two_member_org(client_fresh, accept_as):
    """dev-user (yönetici) + davetle katılan avukat. avukat'ın userId'sini döndürür."""
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    inv = client_fresh.post("/api/invitations", json={"email": "avukat@b.com", "role": "avukat"}).json()
    accept_as(sub="sb-2", email="avukat@b.com", token=inv["token"])
    members = client_fresh.get("/api/memberships").json()
    avukat = next(m for m in members if not m["isSelf"])
    return avukat["userId"]


def test_list_members_returns_org_roster(client_fresh, accept_as):
    _two_member_org(client_fresh, accept_as)
    members = client_fresh.get("/api/memberships").json()
    assert len(members) == 2
    roles = {m["email"]: m["role"] for m in members}
    assert roles["dev@kvkkyonetim.local"] == "yonetici"
    assert roles["avukat@b.com"] == "avukat"
    assert sum(1 for m in members if m["isSelf"]) == 1  # tam olarak bir 'ben'


def test_admin_changes_member_role(client_fresh, accept_as):
    avukat_id = _two_member_org(client_fresh, accept_as)
    r = client_fresh.patch(f"/api/memberships/{avukat_id}", json={"role": "yonetici"})
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "yonetici"


def test_cannot_demote_last_admin(client_fresh, accept_as):
    _two_member_org(client_fresh, accept_as)
    # dev-user tek yönetici; kendini avukata düşürmeye çalış → 409 last_admin
    me = next(m for m in client_fresh.get("/api/memberships").json() if m["isSelf"])
    r = client_fresh.patch(f"/api/memberships/{me['userId']}", json={"role": "avukat"})
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "last_admin"


def test_admin_removes_member(client_fresh, accept_as):
    avukat_id = _two_member_org(client_fresh, accept_as)
    r = client_fresh.delete(f"/api/memberships/{avukat_id}")
    assert r.status_code == 204, r.text
    members = client_fresh.get("/api/memberships").json()
    assert len(members) == 1
    assert members[0]["email"] == "dev@kvkkyonetim.local"


def test_cannot_remove_last_admin(client_fresh, accept_as):
    _two_member_org(client_fresh, accept_as)
    me = next(m for m in client_fresh.get("/api/memberships").json() if m["isSelf"])
    r = client_fresh.delete(f"/api/memberships/{me['userId']}")
    assert r.status_code == 409, r.text
    assert r.json()["detail"]["code"] == "last_admin"


def test_remove_unknown_member_404(client_fresh, accept_as):
    _two_member_org(client_fresh, accept_as)
    r = client_fresh.delete(f"/api/memberships/{uuid.uuid4()}")
    assert r.status_code == 404, r.text


def test_invalid_role_rejected(client_fresh, accept_as):
    avukat_id = _two_member_org(client_fresh, accept_as)
    r = client_fresh.patch(f"/api/memberships/{avukat_id}", json={"role": "hacker"})
    assert r.status_code == 422, r.text


def test_avukat_cannot_manage_members(client_fresh, accept_as):
    avukat_id = _two_member_org(client_fresh, accept_as)
    # Kimliği avukat'a çevir → PATCH/DELETE 403, GET yine serbest
    app.dependency_overrides[get_current_identity] = lambda: Identity(
        user_id=uuid.uuid4(),
        org_id=uuid.UUID(int=0),
        role="avukat",
        email="avukat@b.com",
    )
    try:
        assert client_fresh.patch(f"/api/memberships/{avukat_id}", json={"role": "yonetici"}).status_code == 403
        assert client_fresh.delete(f"/api/memberships/{avukat_id}").status_code == 403
        assert client_fresh.get("/api/memberships").status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_identity, None)
