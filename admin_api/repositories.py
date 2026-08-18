"""admin-api salt-okunur repository katmanı.

Rollup-only: yalnızca `platform_metrics_daily`'yi okur — kiracı tablolarına ASLA dokunmaz,
cross-tenant tarama/`begin_provisioning` yok (bkz. Task 7, ayrı — canlı tek-org okuma).
"""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import PlatformMetricDaily


class PlatformMetricsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def overview(self) -> dict[str, float]:
        """Her metric_key için en güncel günün değeri."""
        latest_per_key = (
            select(
                PlatformMetricDaily.metric_key,
                func.max(PlatformMetricDaily.day).label("max_day"),
            )
            .group_by(PlatformMetricDaily.metric_key)
            .subquery()
        )
        rows = self._session.execute(
            select(PlatformMetricDaily.metric_key, PlatformMetricDaily.value_numeric).join(
                latest_per_key,
                (PlatformMetricDaily.metric_key == latest_per_key.c.metric_key)
                & (PlatformMetricDaily.day == latest_per_key.c.max_day),
            )
        ).all()
        return {metric_key: float(value) for metric_key, value in rows}

    def timeseries(self, metric_key: str, days: int) -> list[dict]:
        """`(metric_key, day)` indeksini kullanarak son `days` günün noktalarını döndürür."""
        cutoff = date.today() - timedelta(days=days)
        rows = self._session.execute(
            select(PlatformMetricDaily.day, PlatformMetricDaily.value_numeric)
            .where(
                PlatformMetricDaily.metric_key == metric_key,
                PlatformMetricDaily.day >= cutoff,
            )
            .order_by(PlatformMetricDaily.day)
        ).all()
        return [{"day": day, "value": float(value)} for day, value in rows]
