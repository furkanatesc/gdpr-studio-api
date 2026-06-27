import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.billing.entitlement import (
    FREE_MONTHLY_QUOTA,
    Entitlement,
    current_period,
    resolve_entitlement,
)
from app.billing.repositories import SubscriptionRepository, UsageRepository
from app.config import Settings
from app.db import Base
from app.models import Organization


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield s
    s.close()


def _org(session) -> uuid.UUID:
    org = Organization(name="Acme")
    session.add(org)
    session.flush()
    return org.id


def test_current_period_format():
    assert current_period(datetime(2026, 6, 26, tzinfo=UTC)) == "2026-06"


def test_no_subscription_is_free_with_quota(session):
    org_id = _org(session)
    ent = resolve_entitlement(session, org_id)
    assert isinstance(ent, Entitlement)
    assert ent.plan == "baslangic" and ent.quota == FREE_MONTHLY_QUOTA and ent.used == 0


def test_used_reflects_current_period(session):
    org_id = _org(session)
    UsageRepository(session).increment(org_id, current_period())
    assert resolve_entitlement(session, org_id).used == 1


def test_paid_plan_has_no_quota(session):
    org_id = _org(session)
    SubscriptionRepository(session).upsert(org_id, plan="standart", interval="year", status="active")
    ent = resolve_entitlement(session, org_id)
    assert ent.plan == "standart" and ent.quota is None


def test_price_map_and_lookup():
    s = Settings(
        _env_file=None,
        stripe_secret_key="sk_test_x",
        stripe_price_standart_month="price_sm",
        stripe_price_standart_year="price_sy",
        stripe_price_premium_month="price_pm",
        stripe_price_premium_year="price_py",
    )
    assert s.billing_enabled is True
    assert s.price_map["price_sy"] == ("standart", "year")
    assert s.price_for("premium", "month") == "price_pm"
    assert s.price_for("standart", "month") == "price_sm"


def test_billing_disabled_when_no_key():
    assert Settings(_env_file=None).billing_enabled is False


# --- Fix #1: kota, abonelik durumuna bağlıdır ---

def test_paid_past_due_gets_free_quota(session):
    """past_due ücretli plan: kota ücretsiz plana düşer; plan ve durum gerçek değerleriyle raporlanır."""
    org_id = _org(session)
    SubscriptionRepository(session).upsert(org_id, plan="premium", status="past_due")
    ent = resolve_entitlement(session, org_id)
    assert ent.quota == FREE_MONTHLY_QUOTA
    assert ent.plan == "premium"
    assert ent.status == "past_due"


def test_paid_canceled_gets_free_quota(session):
    """canceled ücretli plan: kota ücretsiz plana düşer; plan ve durum gerçek değerleriyle raporlanır."""
    org_id = _org(session)
    SubscriptionRepository(session).upsert(org_id, plan="standart", status="canceled")
    ent = resolve_entitlement(session, org_id)
    assert ent.quota == FREE_MONTHLY_QUOTA
    assert ent.plan == "standart"
    assert ent.status == "canceled"
