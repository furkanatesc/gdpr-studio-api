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
    record_generation_usage(
        db_session, settings, org_id,
        model="claude-sonnet-4-6", input_tokens=0, output_tokens=0, byok=False,
    )
    assert UsageRepository(db_session).get_count(org_id, current_period()) == 1


def test_record_managed_accumulates_cost(db_session):
    from app.billing.pricing import cost_micros
    from app.billing.quota import record_generation_usage

    settings = config_module.Settings(_env_file=None, stripe_secret_key="sk_test_x")
    org_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    record_generation_usage(
        db_session, settings, org_id,
        model="claude-sonnet-4-6", input_tokens=100, output_tokens=200, byok=False,
    )
    repo = UsageRepository(db_session)
    assert repo.get_count(org_id, current_period()) == 1
    assert repo.get_cost(org_id, current_period()) == cost_micros("claude-sonnet-4-6", 100, 200)


def test_record_byok_counts_doc_but_no_cost(db_session):
    from app.billing.quota import record_generation_usage

    settings = config_module.Settings(_env_file=None, stripe_secret_key="sk_test_x")
    org_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    record_generation_usage(
        db_session, settings, org_id,
        model="claude-sonnet-4-6", input_tokens=100, output_tokens=200, byok=True,
    )
    repo = UsageRepository(db_session)
    assert repo.get_count(org_id, current_period()) == 1
    assert repo.get_cost(org_id, current_period()) == 0


def test_cost_budget_blocks_paid_org(client, db_session):
    """premium+active org (doküman kotası yok) birikmiş maliyet ≥ bütçe → 402 cost_budget_exceeded."""
    from app.billing.repositories import SubscriptionRepository

    _enable_billing_no_key_paid()
    org_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    SubscriptionRepository(db_session).upsert(org_id, plan="premium", status="active")
    # premium bütçesi 150_000_000 micros ($150) → tam tavanda
    UsageRepository(db_session).add_cost(org_id, current_period(), 0, 0, 150_000_000)
    db_session.commit()
    r = client.post("/api/generate", json={"type": "aydinlatma"})
    assert r.status_code == 402
    assert r.json()["detail"]["code"] == "cost_budget_exceeded"


def test_cost_budget_allows_under_budget(client, db_session):
    """maliyet < bütçe → kota geçer; managed anahtarsız üretim 400 (maliyet 402 DEĞİL)."""
    from app.billing.repositories import SubscriptionRepository

    _enable_billing_no_key_paid()
    org_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    SubscriptionRepository(db_session).upsert(org_id, plan="premium", status="active")
    UsageRepository(db_session).add_cost(org_id, current_period(), 0, 0, 1_000_000)  # $1 < $150
    db_session.commit()
    r = client.post("/api/generate", json={"type": "aydinlatma"})
    assert r.status_code == 400


def test_cost_budget_skipped_for_byok(client, db_session):
    """BYOK (X-Anthropic-Key) → maliyet kontrolü atlanır; tavan dolu olsa bile 402 cost değil."""
    from app.billing.repositories import SubscriptionRepository

    _enable_billing_no_key_paid()
    org_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    SubscriptionRepository(db_session).upsert(org_id, plan="premium", status="active")
    UsageRepository(db_session).add_cost(org_id, current_period(), 0, 0, 150_000_000)
    db_session.commit()
    r = client.post(
        "/api/generate", json={"type": "aydinlatma"}, headers={"X-Anthropic-Key": "sk-ant-byok-fake"}
    )
    # BYOK anahtarıyla üretim yoluna girer (sahte anahtar → gerçek çağrı patlar, 502/4xx) — ama 402 maliyet DEĞİL
    assert r.status_code != 402


# --- Fix #1 uçtan uca: past_due ücretli org kota kapısına takılmalı ---

def test_quota_blocks_past_due_paid_org_at_five(client, db_session):
    """past_due ücretli org, 5 kullanım sonrası 402 almalı (aktif olmayan abonelik → ücretsiz kota)."""
    from app.billing.repositories import SubscriptionRepository
    _enable_billing_no_key_paid()
    org_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    SubscriptionRepository(db_session).upsert(org_id, plan="premium", status="past_due")
    for _ in range(5):
        UsageRepository(db_session).increment(org_id, current_period())
    db_session.commit()
    r = client.post("/api/generate", json={"type": "aydinlatma"})
    assert r.status_code == 402
    assert r.json()["detail"]["code"] == "quota_exceeded"


def test_quota_allows_active_paid_org_regardless(client, db_session):
    """Aktif ücretli org sınırsız erişime sahip; 10 kullanımda bile 402 yok."""
    from app.billing.repositories import SubscriptionRepository
    _enable_billing_no_key_paid()
    org_id = uuid.UUID("00000000-0000-0000-0000-000000000002")
    SubscriptionRepository(db_session).upsert(org_id, plan="premium", status="active")
    for _ in range(10):
        UsageRepository(db_session).increment(org_id, current_period())
    db_session.commit()
    r = client.post("/api/generate", json={"type": "aydinlatma"})
    # Kota engeli yok → API anahtarsız üretim 400 döner
    assert r.status_code == 400
