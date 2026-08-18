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

    def overview(self) -> list[dict]:
        """Her `(metric_key, dims)` kombinasyonu için en güncel günün satırı.

        Dims'i ASLA toplama/collapse etme (bkz. fix brief): `subs_active` her plan için
        ayrı satır döner, dims'siz metrikler ({}) tek satır döner.
        """
        latest_per_key = (
            select(
                PlatformMetricDaily.metric_key,
                func.max(PlatformMetricDaily.day).label("max_day"),
            )
            .group_by(PlatformMetricDaily.metric_key)
            .subquery()
        )
        rows = self._session.execute(
            select(
                PlatformMetricDaily.metric_key,
                PlatformMetricDaily.day,
                PlatformMetricDaily.dims,
                PlatformMetricDaily.value_numeric,
            ).join(
                latest_per_key,
                (PlatformMetricDaily.metric_key == latest_per_key.c.metric_key)
                & (PlatformMetricDaily.day == latest_per_key.c.max_day),
            )
        ).all()
        return [
            {
                "metric_key": metric_key,
                "day": day,
                "dims": dims,
                "value": float(value),
            }
            for metric_key, day, dims, value in sorted(
                rows, key=lambda r: (r[0], sorted(r[2].items()))
            )
        ]

    def timeseries(self, metric_key: str, days: int) -> list[dict]:
        """`(metric_key, day)` indeksini kullanarak son `days` günün noktalarını döndürür.

        Dims'li metrikler (ör. `subs_active`) her gün için birden çok noktaya karşılık gelir;
        her nokta kendi `dims`'ini taşır — toplama/collapse yok.
        """
        cutoff = date.today() - timedelta(days=days)
        rows = self._session.execute(
            select(
                PlatformMetricDaily.day,
                PlatformMetricDaily.dims,
                PlatformMetricDaily.value_numeric,
            ).where(
                PlatformMetricDaily.metric_key == metric_key,
                PlatformMetricDaily.day >= cutoff,
            )
        ).all()
        ordered = sorted(rows, key=lambda r: (r[0], sorted(r[1].items())))
        return [{"day": day, "dims": dims, "value": float(value)} for day, dims, value in ordered]
