import app.billing.stripe_client as sc
import app.config as config_module


def _enable_billing():
    config_module._settings = config_module.Settings(
        _env_file=None,
        managed_anthropic_api_key="",
        allowed_origins="http://localhost:3000",
        redis_url="",
        supabase_project_url="",
        auth_dev_bypass=True,
        environment="development",
        stripe_secret_key="sk_test_x",
        stripe_webhook_secret="whsec_x",
        stripe_price_standart_year="price_sy",
        stripe_price_premium_month="price_pm",
    )


def test_status_defaults_to_free(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    r = client_fresh.get("/api/billing/status")
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "baslangic"
    assert body["usage"] == {"used": 0, "quota": 5}
    assert body["canManage"] is True  # dev kimliği yonetici


def test_checkout_returns_url(client_fresh, monkeypatch):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    _enable_billing()
    monkeypatch.setattr(sc, "create_checkout_session", lambda *a, **k: "https://checkout/abc")
    r = client_fresh.post("/api/billing/checkout", json={"plan": "standart", "interval": "year"})
    assert r.status_code == 200 and r.json() == {"url": "https://checkout/abc"}


def test_checkout_rejects_unknown_plan(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    _enable_billing()
    r = client_fresh.post("/api/billing/checkout", json={"plan": "altin", "interval": "year"})
    assert r.status_code == 422


def test_checkout_503_when_billing_disabled(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    # _enable_billing çağrılmadı → stripe_secret_key boş
    r = client_fresh.post("/api/billing/checkout", json={"plan": "standart", "interval": "year"})
    assert r.status_code == 503


def test_portal_409_without_customer(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    _enable_billing()
    r = client_fresh.post("/api/billing/portal")
    assert r.status_code == 409


def test_checkout_forbidden_for_avukat(client_fresh, db_session, monkeypatch):
    # bootstrap ile yonetici org'u kur, sonra kimliği avukat'a düşür
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    _enable_billing()
    from app.auth.identity import Identity, get_current_identity
    from app.main import app
    from app.models import Membership
    m = db_session.query(Membership).first()
    app.dependency_overrides[get_current_identity] = lambda: Identity(
        user_id=m.user_id, org_id=m.org_id, role="avukat", email="a@x.io"
    )
    try:
        r = client_fresh.post("/api/billing/checkout", json={"plan": "standart", "interval": "year"})
        assert r.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_identity, None)
