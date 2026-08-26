"""Günlük platform metrik rollup job'u (H5 platform admin).

`platform_metrics_daily` tablosuna gün bazlı, idempotent (UPSERT) satırlar yazar:
`tenants_active` (aktif org sayısı) ve `subs_active` (plan başına aktif abonelik sayısı).

Prod'da `kvkk_metrics_job` rolüyle, kendi `METRICS_JOB_DATABASE_URL`'iyle ayrı bir
zamanlanmış işten çalışır (Railway cron / GitHub Actions / pg_cron) — servis
açılışında ÇALIŞTIRILMAZ. `main()` tek-koşucu güvencesi için `pg_advisory_lock`
kullanır (yalnız Postgres'te; sqlite/dev'de no-op).

`main()` bağlantı motorunu `get_admin_engine()` (kvkk_admin_ro) İLE DEĞİL, doğrudan
`METRICS_JOB_DATABASE_URL`'den kurar — rollup job, admin-api'nin salt-okunur rolünden
ayrı, en-az-yetki `kvkk_metrics_job` rolüyle çalışmalıdır (bkz. migration 0020).
"""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.auth.tenant_session import begin_provisioning, end_provisioning
from app.models import Organization, PlatformMetricDaily, Subscription

_ADVISORY_LOCK_KEY = 5051


def _upsert(session, day: date, key: str, value, dims: dict | None = None) -> None:
    """Dialect-aware idempotent UPSERT (PREFLIGHT ruling 2026-08-17 — plandaki `_upsert`
    yalnız postgres'e özgü `pg_insert(...).on_conflict_do_update(...)` kullanıyordu, bu
    sqlite birim testinde çöker). `app/billing/repositories.py`'deki `usage_counters`
    dialect-aware ON CONFLICT deseninin aynısını izler: dialect `session.bind.dialect.name`
    ile tespit edilir; postgres'te isimli constraint, sqlite'ta index_elements kullanılır.
    """
    dims = dims or {}
    table = PlatformMetricDaily.__table__
    set_ = {"value_numeric": value, "computed_at": func.now()}
    if session.bind.dialect.name == "postgresql":
        stmt = pg_insert(table).values(day=day, metric_key=key, dims=dims, value_numeric=value)
        stmt = stmt.on_conflict_do_update(constraint="uq_platform_metrics_daily", set_=set_)
    else:
        stmt = sqlite_insert(table).values(day=day, metric_key=key, dims=dims, value_numeric=value)
        stmt = stmt.on_conflict_do_update(index_elements=["day", "metric_key", "dims"], set_=set_)
    session.execute(stmt)


def compute_daily(session, day: date) -> None:
    """Bir günün metriklerini hesaplar ve upsert eder.

    Çok-kiracılı (cross-tenant) SELECT'ler `begin_provisioning`/`end_provisioning` ile
    sarmalanır (Postgres'te transaction-local RLS bypass açar/kapar; sqlite'ta no-op).
    `commit()` bypass GUC'unu sıfırladığı için `end_provisioning` her koşulda (finally)
    ayrıca çağrılır — GUC zaten sıfırlanmışsa bu no-op'tur.
    """
    begin_provisioning(session)
    try:
        active = session.execute(
            select(func.count()).select_from(Organization).where(Organization.status == "active")
        ).scalar()
        _upsert(session, day, "tenants_active", active)

        rows = session.execute(
            select(Subscription.plan, func.count())
            .where(Subscription.status == "active")
            .group_by(Subscription.plan)
        ).all()
        for plan, cnt in rows:
            _upsert(session, day, "subs_active", cnt, {"plan": plan})

        session.commit()
    finally:
        end_provisioning(session)


def _utc_today() -> date:
    """Rollup gün referansı = UTC bugünü (yerel `date.today()` gün sınırında kayar)."""
    return datetime.now(UTC).date()


def backfill(session, since: date) -> None:
    """`since` gününden bugüne (dahil) her gün için `compute_daily` çalıştırır."""
    d = since
    today = _utc_today()
    while d <= today:
        compute_daily(session, d)
        d = d + timedelta(days=1)


def _try_advisory_lock(session) -> bool:
    """Tek-koşucu kilidi (yalnız Postgres'te); Postgres dışı dialect'lerde no-op → True döner."""
    if session.bind.dialect.name != "postgresql":
        return True
    return bool(session.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": _ADVISORY_LOCK_KEY}).scalar())


def _advisory_unlock(session) -> None:
    if session.bind.dialect.name != "postgresql":
        return
    session.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _ADVISORY_LOCK_KEY})


def main() -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.config import normalize_pg_url

    from .config import get_admin_settings

    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", help="YYYY-MM-DD — verilirse o günden bugüne backfill yapar")
    args = ap.parse_args()

    settings = get_admin_settings()
    # kvkk_admin_ro DEĞİL: rollup job kendi en-az-yetki rolüyle bağlanmalı. Boşsa
    # admin_database_url'e düşer (dev/test kolaylığı) — prod MUTLAKA
    # METRICS_JOB_DATABASE_URL'i kvkk_metrics_job rolüne ayarlamalıdır.
    job_url = settings.metrics_job_database_url or settings.admin_database_url
    engine = create_engine(normalize_pg_url(job_url), future=True)
    sess = sessionmaker(bind=engine, future=True)()
    try:
        if not _try_advisory_lock(sess):
            print("metrics job: another runner holds the lock, skipping")
            return
        try:
            if args.backfill:
                backfill(sess, date.fromisoformat(args.backfill))
            else:
                compute_daily(sess, _utc_today())
        finally:
            _advisory_unlock(sess)
    finally:
        sess.close()


if __name__ == "__main__":
    main()
