import itertools
from datetime import date

import pytest
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.sql.dml import Insert

from admin_api.metrics_job import compute_daily
from app.db import Base
from app.models import Organization, PlatformMetricDaily

_DAY = date(2026, 8, 17)


@pytest.fixture()
def admin_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    # sqlite yalnız plain INTEGER PK'yı rowid autoincrement'e eşler; PlatformMetricDaily.id
    # BigInteger olduğundan sqlite otomatik atamaz (bkz tests/admin/test_admin_audit.py — aynı
    # gotcha). O testte ORM `session.add()` kullanıldığı için mapper-level `before_insert`
    # event'i yeterliydi; burada PREFLIGHT ruling gereği `_upsert` Core-level
    # `session.execute(insert(table)...)` kullanıyor (ON CONFLICT desteği için), bu da ORM
    # mapper event'lerini atlar. Bu yüzden aynı fikri connection-level `before_execute`
    # event'iyle uyguluyoruz: yalnız platform_metrics_daily'e giden INSERT'lere sıralı id ekler
    # (ON CONFLICT DO UPDATE dallanırsa eklenen id zaten yok sayılır — çakışan satırın id'si
    # değişmez). Model/migration'a dokunulmaz; yalnız test-only şim.
    counter = itertools.count(1)

    def _assign_id(conn, clauseelement, multiparams, params, execution_options):
        if isinstance(clauseelement, Insert) and clauseelement.table.name == "platform_metrics_daily":
            clauseelement = clauseelement.values(id=next(counter))
        return clauseelement, multiparams, params

    event.listen(engine, "before_execute", _assign_id, retval=True)
    try:
        yield sessionmaker(bind=engine, future=True, expire_on_commit=False)()
    finally:
        event.remove(engine, "before_execute", _assign_id)


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
