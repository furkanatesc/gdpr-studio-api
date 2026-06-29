import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.billing.repositories import (
    StripeEventRepository,
    SubscriptionRepository,
    UsageRepository,
)
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


def test_subscription_upsert_creates_then_updates(session):
    org_id = _org(session)
    repo = SubscriptionRepository(session)
    sub = repo.upsert(org_id, customer_id="cus_1", subscription_id="sub_1")
    assert sub.plan == "baslangic" and sub.stripe_customer_id == "cus_1"
    again = repo.upsert(org_id, plan="standart", interval="year", status="active")
    assert again.id == sub.id and again.plan == "standart" and again.interval == "year"
    assert repo.get_by_customer("cus_1").id == sub.id


def test_set_status_by_customer(session):
    org_id = _org(session)
    repo = SubscriptionRepository(session)
    repo.upsert(org_id, customer_id="cus_9", plan="standart", status="active")
    assert repo.set_status_by_customer("cus_9", "past_due") is True
    assert repo.get_by_org(org_id).status == "past_due"
    assert repo.set_status_by_customer("cus_absent", "past_due") is False


def test_usage_increment_per_period(session):
    org_id = _org(session)
    repo = UsageRepository(session)
    assert repo.get_count(org_id, "2026-06") == 0
    assert repo.increment(org_id, "2026-06") == 1
    assert repo.increment(org_id, "2026-06") == 2
    assert repo.increment(org_id, "2026-07") == 1  # yeni ay → ayrı sayaç
    assert repo.get_count(org_id, "2026-06") == 2


def test_stripe_event_idempotency(session):
    repo = StripeEventRepository(session)
    assert repo.seen("evt_1") is False
    repo.record("evt_1", "checkout.session.completed")
    assert repo.seen("evt_1") is True


def test_get_cost_zero_when_no_row(session):
    import uuid

    repo = UsageRepository(session)
    assert repo.get_cost(uuid.uuid4(), "2026-06") == 0


def test_add_cost_accumulates(session):
    import uuid

    org_id = uuid.uuid4()
    repo = UsageRepository(session)
    repo.add_cost(org_id, "2026-06", 100, 200, 5000)
    repo.add_cost(org_id, "2026-06", 10, 20, 500)
    assert repo.get_cost(org_id, "2026-06") == 5500
    row = repo._row(org_id, "2026-06")
    assert row.input_tokens == 110
    assert row.output_tokens == 220
