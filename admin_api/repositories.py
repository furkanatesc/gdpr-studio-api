"""admin-api salt-okunur repository katmanı.

Rollup-only: yalnızca `platform_metrics_daily`'yi okur — kiracı tablolarına ASLA dokunmaz,
cross-tenant tarama/`begin_provisioning` yok (bkz. Task 7, ayrı — canlı tek-org okuma).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.auth.tenant_session import begin_provisioning, end_provisioning, set_org_context
from app.models import Membership, Organization, PlatformMetricDaily, Subscription, UsageCounter


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


def _parse_tenant_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    created_at_raw, id_raw = cursor.rsplit("|", 1)
    return datetime.fromisoformat(created_at_raw), uuid.UUID(id_raw)


def _encode_tenant_cursor(created_at: datetime, org_id: uuid.UUID) -> str:
    return f"{created_at.isoformat()}|{org_id}"


class TenantAdminRepository:
    """Kiracı listesi (rollup+küçük indeksli join) + tek-org canlı detay.

    Liste: `organizations` LEFT JOIN `subscriptions` — cross-tenant
    `generated_documents`/`usage_counters`/`client_documents` TARAMASI YOK.
    Detay: `set_org_context` ile tek-org kapsamına girip subscription/usage/member
    sayısını okur (bkz. Task 7 brief).
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def list(
        self,
        cursor: str | None = None,
        q: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> dict:
        stmt = select(Organization, Subscription).outerjoin(
            Subscription, Subscription.org_id == Organization.id
        )
        if q:
            stmt = stmt.where(func.lower(Organization.name).contains(func.lower(q)))
        if status:
            stmt = stmt.where(Organization.status == status)
        if cursor:
            cursor_created_at, cursor_id = _parse_tenant_cursor(cursor)
            stmt = stmt.where(
                or_(
                    Organization.created_at < cursor_created_at,
                    and_(
                        Organization.created_at == cursor_created_at,
                        Organization.id < cursor_id,
                    ),
                )
            )
        stmt = stmt.order_by(Organization.created_at.desc(), Organization.id.desc()).limit(
            limit + 1
        )
        begin_provisioning(self._session)
        try:
            rows = self._session.execute(stmt).all()
        finally:
            end_provisioning(self._session)
        has_more = len(rows) > limit
        page_rows = rows[:limit]

        items = [
            {
                "id": org.id,
                "name": org.name,
                "sector": org.sector,
                "status": org.status,
                "created_at": org.created_at,
                "plan": sub.plan if sub else None,
                "subscription_status": sub.status if sub else None,
            }
            for org, sub in page_rows
        ]

        next_cursor = None
        if has_more and page_rows:
            last_org, _ = page_rows[-1]
            next_cursor = _encode_tenant_cursor(last_org.created_at, last_org.id)

        return {"items": items, "next_cursor": next_cursor}

    def detail(self, org_id: uuid.UUID) -> dict | None:
        set_org_context(self._session, org_id)

        org = self._session.execute(
            select(Organization).where(Organization.id == org_id)
        ).scalar_one_or_none()
        if org is None:
            return None

        sub = self._session.execute(
            select(Subscription).where(Subscription.org_id == org_id)
        ).scalar_one_or_none()

        member_count = self._session.execute(
            select(func.count()).select_from(Membership).where(Membership.org_id == org_id)
        ).scalar_one()

        usage = self._session.execute(
            select(UsageCounter)
            .where(UsageCounter.org_id == org_id)
            .order_by(UsageCounter.period.desc())
            .limit(1)
        ).scalar_one_or_none()

        return {
            "id": org.id,
            "name": org.name,
            "sector": org.sector,
            "status": org.status,
            "created_at": org.created_at,
            "plan": sub.plan if sub else None,
            "subscription_status": sub.status if sub else None,
            "current_period_end": sub.current_period_end if sub else None,
            "member_count": member_count,
            "usage": (
                {
                    "period": usage.period,
                    "doc_count": usage.doc_count,
                    "cost_micros": usage.cost_micros,
                    "input_tokens": usage.input_tokens,
                    "output_tokens": usage.output_tokens,
                }
                if usage
                else None
            ),
        }
