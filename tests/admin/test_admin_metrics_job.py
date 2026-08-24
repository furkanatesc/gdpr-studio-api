from datetime import date, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from admin_api.metrics_job import backfill, compute_daily
from app.db import Base
from app.models import Organization, PlatformMetricDaily, Subscription

_DAY = date(2026, 8, 17)


@pytest.fixture()
def admin_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, future=True, expire_on_commit=False)()


@pytest.fixture()
def seed_orgs(admin_db):
    orgs = [Organization(name=f"Org {i}", status="active") for i in range(3)]
    orgs.append(Organization(name="Suspended Org", status="suspended"))
    admin_db.add_all(orgs)
    admin_db.commit()
    return orgs


def _metric(session, key, day):
    return session.execute(
        select(PlatformMetricDaily.value_numeric).where(
            PlatformMetricDaily.day == day, PlatformMetricDaily.metric_key == key
        )
    ).scalar()


def _count_rows(session, key, day):
    return len(
        session.execute(
            select(PlatformMetricDaily.id).where(
                PlatformMetricDaily.day == day, PlatformMetricDaily.metric_key == key
            )
        ).all()
    )


def _rows(session, key, day):
    """(dims, value) tuples for every row under `key`/`day` — for asserting per-dims UPSERT."""
    return session.execute(
        select(PlatformMetricDaily.dims, PlatformMetricDaily.value_numeric).where(
            PlatformMetricDaily.day == day, PlatformMetricDaily.metric_key == key
        )
    ).all()


def test_compute_daily_writes_tenant_counts(admin_db, seed_orgs):
    compute_daily(admin_db, _DAY)
    assert _metric(admin_db, "tenants_active", _DAY) == 3


def test_compute_daily_is_idempotent(admin_db, seed_orgs):
    compute_daily(admin_db, _DAY)
    compute_daily(admin_db, _DAY)
    assert _count_rows(admin_db, "tenants_active", _DAY) == 1
    assert _metric(admin_db, "tenants_active", _DAY) == 3


def test_compute_daily_writes_subs_active_per_plan(admin_db, seed_orgs):
    subs = [
        Subscription(org_id=seed_orgs[0].id, plan="baslangic", status="active"),
        Subscription(org_id=seed_orgs[1].id, plan="baslangic", status="active"),
        Subscription(org_id=seed_orgs[2].id, plan="premium", status="active"),
        # canceled — must NOT be counted
        Subscription(org_id=seed_orgs[3].id, plan="premium", status="canceled"),
    ]
    admin_db.add_all(subs)
    admin_db.commit()

    compute_daily(admin_db, _DAY)

    rows = {dims["plan"]: value for dims, value in _rows(admin_db, "subs_active", _DAY)}
    assert rows == {"baslangic": 2, "premium": 1}


def test_backfill_writes_daily_rows_for_each_day_in_range(admin_db, seed_orgs):
    since = date.today() - timedelta(days=2)
    backfill(admin_db, since=since)

    d = since
    today = date.today()
    while d <= today:
        assert _metric(admin_db, "tenants_active", d) == 3
        d = d + timedelta(days=1)
