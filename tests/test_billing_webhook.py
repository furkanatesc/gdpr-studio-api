import app.billing.stripe_client as sc
import app.config as config_module
from app.billing.repositories import StripeEventRepository, SubscriptionRepository
from app.models import Organization
from app.modules.billing import _status_map


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


def _org(db_session) -> str:
    org = Organization(name="Acme")
    db_session.add(org)
    db_session.commit()
    return str(org.id)


def _post(client, monkeypatch, event):
    monkeypatch.setattr(sc, "construct_event", lambda settings, payload, sig: event)
    return client.post("/api/billing/webhook", content=b"{}", headers={"Stripe-Signature": "sig"})


def test_invalid_signature_returns_400(client_fresh, monkeypatch):
    _enable_billing()

    def _raise(settings, payload, sig):
        raise ValueError("bad sig")

    monkeypatch.setattr(sc, "construct_event", _raise)
    r = client_fresh.post("/api/billing/webhook", content=b"{}", headers={"Stripe-Signature": "x"})
    assert r.status_code == 400


def test_subscription_updated_sets_plan(client_fresh, db_session, monkeypatch):
    _enable_billing()
    org_id = _org(db_session)
    event = {
        "id": "evt_1",
        "type": "customer.subscription.updated",
        "data": {"object": {
            "id": "sub_1", "customer": "cus_1", "status": "active",
            "current_period_end": 1782000000,
            "metadata": {"org_id": org_id},
            "items": {"data": [{"price": {"id": "price_sy"}}]},
        }},
    }
    r = _post(client_fresh, monkeypatch, event)
    assert r.status_code == 200
    sub = SubscriptionRepository(db_session).get_by_org(__import__("uuid").UUID(org_id))
    assert sub.plan == "standart" and sub.interval == "year" and sub.status == "active"
    assert sub.stripe_customer_id == "cus_1"


def test_idempotent_replay_is_noop(client_fresh, db_session, monkeypatch):
    _enable_billing()
    org_id = _org(db_session)
    event = {
        "id": "evt_dup",
        "type": "customer.subscription.updated",
        "data": {"object": {
            "id": "sub_1", "customer": "cus_1", "status": "active",
            "current_period_end": 1782000000, "metadata": {"org_id": org_id},
            "items": {"data": [{"price": {"id": "price_pm"}}]},
        }},
    }
    _post(client_fresh, monkeypatch, event)
    # ikinci kez: plan'ı elle değiştir, replay etkilememeli
    import uuid
    SubscriptionRepository(db_session).upsert(uuid.UUID(org_id), plan="baslangic")
    db_session.commit()
    _post(client_fresh, monkeypatch, event)
    assert SubscriptionRepository(db_session).get_by_org(uuid.UUID(org_id)).plan == "baslangic"
    assert StripeEventRepository(db_session).seen("evt_dup") is True


def test_subscription_deleted_downgrades(client_fresh, db_session, monkeypatch):
    _enable_billing()
    org_id = _org(db_session)
    import uuid
    SubscriptionRepository(db_session).upsert(
        uuid.UUID(org_id), customer_id="cus_1", plan="standart", interval="year", status="active"
    )
    db_session.commit()
    event = {
        "id": "evt_del",
        "type": "customer.subscription.deleted",
        "data": {"object": {"id": "sub_1", "customer": "cus_1", "metadata": {"org_id": org_id}}},
    }
    _post(client_fresh, monkeypatch, event)
    sub = SubscriptionRepository(db_session).get_by_org(uuid.UUID(org_id))
    assert sub.plan == "baslangic" and sub.status == "canceled"


def test_payment_failed_sets_past_due(client_fresh, db_session, monkeypatch):
    _enable_billing()
    org_id = _org(db_session)
    import uuid
    SubscriptionRepository(db_session).upsert(
        uuid.UUID(org_id), customer_id="cus_1", plan="standart", status="active"
    )
    db_session.commit()
    event = {
        "id": "evt_fail",
        "type": "invoice.payment_failed",
        "data": {"object": {"customer": "cus_1"}},
    }
    _post(client_fresh, monkeypatch, event)
    assert SubscriptionRepository(db_session).get_by_org(uuid.UUID(org_id)).status == "past_due"


# --- Fix #2: _status_map bilinmeyen durumları kısıtlayıcı yönde eşleştirmeli ---

def test_status_map_known_mappings():
    """Bilinen Stripe durumları doğru iç duruma eşleşmeli."""
    assert _status_map("active") == "active"
    assert _status_map("trialing") == "active"
    assert _status_map("past_due") == "past_due"
    assert _status_map("unpaid") == "past_due"
    assert _status_map("canceled") == "canceled"
    assert _status_map("incomplete_expired") == "canceled"


def test_status_map_unknown_maps_to_canceled():
    """Bilinmeyen Stripe durumları 'canceled' (kısıtlayıcı) yönde eşleşmeli, 'active' değil."""
    assert _status_map("incomplete") == "canceled"
    assert _status_map("paused") == "canceled"
    assert _status_map("some_future_stripe_status") == "canceled"
