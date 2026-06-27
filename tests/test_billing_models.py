from app.db import Base
from app.models import StripeEvent, Subscription, UsageCounter  # noqa: F401


def test_billing_tables_registered():
    names = set(Base.metadata.tables)
    assert {"subscriptions", "usage_counters", "stripe_events"} <= names


def test_subscription_columns():
    cols = {c.name for c in Subscription.__table__.columns}
    assert {
        "id", "org_id", "stripe_customer_id", "stripe_subscription_id",
        "plan", "interval", "status", "current_period_end", "created_at", "updated_at",
    } <= cols
    assert Subscription.__table__.c.org_id.unique is True


def test_usage_counter_unique_constraint():
    uniques = [
        tuple(sorted(col.name for col in c.columns))
        for c in UsageCounter.__table__.constraints
        if c.__class__.__name__ == "UniqueConstraint"
    ]
    assert ("org_id", "period") in uniques
