"""Platform metrik okuma uçları — YALNIZCA `platform_metrics_daily` rollup'unu okur.

Cross-tenant canlı tarama / `begin_provisioning` bypass burada YOK (spec'in yasakladığı
full-scan MVP-trap); tek-org canlı okuma ayrı bir uçtur (Task 7).
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from ..auth import PlatformAdminIdentity, require_platform_admin
from ..db import admin_session
from ..repositories import PlatformMetricsRepository

router = APIRouter(prefix="/admin/metrics", tags=["admin-metrics"])


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class MetricsOverview(_Camel):
    metrics: dict[str, float]


class TimeseriesPoint(_Camel):
    day: date
    value: float


class MetricsTimeseries(_Camel):
    points: list[TimeseriesPoint]


@router.get("/overview", response_model=MetricsOverview)
def get_overview(
    identity: PlatformAdminIdentity = Depends(require_platform_admin),
    session: Session = Depends(admin_session),
) -> MetricsOverview:
    return MetricsOverview(metrics=PlatformMetricsRepository(session).overview())


@router.get("/timeseries", response_model=MetricsTimeseries)
def get_timeseries(
    metric: str,
    range: int = Query(..., ge=1, le=366),
    identity: PlatformAdminIdentity = Depends(require_platform_admin),
    session: Session = Depends(admin_session),
) -> MetricsTimeseries:
    points = PlatformMetricsRepository(session).timeseries(metric, range)
    return MetricsTimeseries(points=[TimeseriesPoint(**point) for point in points])
