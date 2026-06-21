"""Hesap uçları entegrasyon testleri — bootstrap (provision/idempotent) + me.

client_fresh fixture'ı kullanır: get_current_identity override edilmez, dev-bypass
aktif (supabase_project_url=""), DB temiz (users/orgs yok). Gerçek DB akışını test eder.
"""

from __future__ import annotations


def test_bootstrap_creates_org_and_me_returns_it(client_fresh):
    r = client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme Hukuk"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["orgName"] == "Acme Hukuk"
    assert body["role"] == "yonetici"

    r2 = client_fresh.get("/api/auth/me")
    assert r2.status_code == 200
    assert r2.json()["orgId"] == body["orgId"]


def test_bootstrap_idempotent(client_fresh):
    a = client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"}).json()
    b = client_fresh.post("/api/auth/bootstrap", json={"orgName": "Başka"}).json()
    assert a["orgId"] == b["orgId"]  # ikinci çağrı yeni kurum açmaz


def test_me_without_account_403(client_fresh):
    # bootstrap çağrılmadı → kullanıcı DB'de yok → get_current_identity 403 döndürür
    assert client_fresh.get("/api/auth/me").status_code == 403


def test_bootstrap_rejects_blank_org_name(client_fresh):
    r = client_fresh.post("/api/auth/bootstrap", json={"orgName": "   "})
    assert r.status_code == 422
