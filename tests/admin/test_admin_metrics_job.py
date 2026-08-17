from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from admin_api.metrics_job import compute_daily
from app.db import Base
from app.models import Organization, PlatformMetricDaily

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


def test_compute_daily_writes_tenant_counts(admin_db, seed_orgs):
    compute_daily(admin_db, _DAY)
    assert _metric(admin_db, "tenants_active", _DAY) == 3


def test_compute_daily_is_idempotent(admin_db, seed_orgs):
    compute_daily(admin_db, _DAY)
    compute_daily(admin_db, _DAY)
    assert _count_rows(admin_db, "tenants_active", _DAY) == 1
    assert _metric(admin_db, "tenants_active", _DAY) == 3
