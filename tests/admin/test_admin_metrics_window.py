"""timeseries pencere sınırı + UTC-tarih referansı (minor takip ticket'i).

- `days=N` isteği TAM N takvim günü döner (bugün dahil), N+1 DEĞİL.
- Pencere `utc_now().date()`'ten hesaplanır (yerel `date.today()` değil) — gün
  sınırında metrics_job'un UTC damgasıyla tutarlı kalır.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import admin_api.metrics_job as metrics_job_module
import admin_api.repositories as repositories_module
from admin_api.repositories import PlatformMetricsRepository
from app.db import Base
from app.models import PlatformMetricDaily

# Gün sınırına yakın erken UTC saati — yerel tz batı-negatifse bir önceki güne kayar.
FIXED_NOW = datetime(2026, 8, 26, 2, 0, 0, tzinfo=UTC)
UTC_TODAY = FIXED_NOW.date()


@pytest.fixture()
def session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    for k in range(4):  # today, today-1, today-2, today-3
        s.add(
            PlatformMetricDaily(
                day=UTC_TODAY - timedelta(days=k),
                metric_key="m",
                dims={},
                value_numeric=k,
            )
        )
    s.commit()
    yield s
    s.close()


def test_timeseries_returns_exactly_n_days_including_today(session, monkeypatch):
    monkeypatch.setattr(repositories_module, "utc_now", lambda: FIXED_NOW)

    points = PlatformMetricsRepository(session).timeseries("m", days=2)

    days = {p["day"] for p in points}
    # days=2 → yalnız {today, today-1}; today-2 HARİÇ (N+1 regresyonu yakalar).
    assert days == {UTC_TODAY, UTC_TODAY - timedelta(days=1)}


def test_backfill_upper_bound_is_utc_today(monkeypatch):
    monkeypatch.setattr(metrics_job_module, "_utc_today", lambda: UTC_TODAY)
    called: list = []
    monkeypatch.setattr(
        metrics_job_module, "compute_daily", lambda _sess, day: called.append(day)
    )

    metrics_job_module.backfill(object(), UTC_TODAY - timedelta(days=1))

    # since=today-1 → {today-1, today} (üst sınır UTC bugünü, yerel değil).
    assert called == [UTC_TODAY - timedelta(days=1), UTC_TODAY]
