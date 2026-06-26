import uuid

import app.config as config_module
from app.billing.entitlement import current_period
from app.billing.repositories import UsageRepository


def _enable_billing_no_key_paid():
    # billing AÇIK (stripe_secret_key var) ama gerçek Stripe çağrısı yok → kota enforce edilir
    config_module._settings = config_module.Settings(
        _env_file=None,
        managed_anthropic_api_key="",
        allowed_origins="http://localhost:3000",
        redis_url="",
        environment="development",
        stripe_secret_key="sk_test_x",
        stripe_webhook_secret="whsec_x",
    )


def test_quota_blocks_after_five(client, db_session):
    # `client` fixture _DEV_IDENTITY (org 000...0002, yonetici) + get_current_identity override kullanır
    _enable_billing_no_key_paid()
    org_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    for _ in range(5):
        UsageRepository(db_session).increment(org_id, current_period())
    db_session.commit()
    # Geçerli minimum GenerateRequest gövdesi {type,...} → body 422 vermez, kota 402 verir
    r = client.post("/api/generate", json={"type": "aydinlatma"})
    assert r.status_code == 402
    assert r.json()["detail"]["code"] == "quota_exceeded"


def test_quota_allows_when_billing_disabled(client, db_session):
    # billing KAPALI (varsayılan `client` ayarı stripe_secret_key boş) → kota yok, anahtarsız üretim 400
    org_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    for _ in range(10):
        UsageRepository(db_session).increment(org_id, current_period())
    db_session.commit()
    r = client.post("/api/generate", json={"type": "aydinlatma"})
    assert r.status_code == 400  # kota değil — anahtarsız üretim hatası (enforcement devre dışı)


def test_record_usage_increments(db_session):
    from app.billing.quota import record_generation_usage
    org_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    settings = config_module.Settings(_env_file=None, stripe_secret_key="sk_test_x")
    record_generation_usage(db_session, settings, org_id)
    assert UsageRepository(db_session).get_count(org_id, current_period()) == 1
