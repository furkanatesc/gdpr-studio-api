"""admin-api salt-okunur repository katmanı.

Rollup-only: `PlatformMetricsRepository`/`TenantAdminRepository` yalnızca `platform_metrics_daily`'yi
okur veya küçük indeksli join'lerle kiracı verisine dokunur — cross-tenant tarama/`begin_provisioning`
yok (bkz. Task 7, ayrı — canlı tek-org okuma). `ImpersonationRepository` back-office
`impersonation_sessions`/`platform_audit_logs` tablolarında çalışır — kiracı verisi OKUMAZ/YAZMAZ
(bkz. Task 8; kapsamlı kiracı okuma proxy'si Task 9'da AYRI).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.auth.tenant_session import begin_provisioning, end_provisioning, set_org_context
from app.models import (
    ImpersonationSession,
    Membership,
    Organization,
    PlatformAdmin,
    PlatformAuditLog,
    PlatformMetricDaily,
    Subscription,
    UsageCounter,
)

from .audit import write_audit


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


def _parse_audit_cursor(cursor: str) -> int:
    return int(cursor)


def _encode_audit_cursor(last_id: int) -> str:
    return str(last_id)


class PlatformAuditRepository:
    """`platform_audit_logs` salt-okunur pager — `id` DESC keyset (PK, indeksli).

    `created_at` yerine `id` ile sıralanır: iki kompozit indeks de `created_at` ile
    BAŞLAMIYOR, bu yüzden `created_at` sıralaması ölçekte seq-scan/sort'a düşer; `id` DESC
    indeksli ve (append-only, artan ekleme sırası nedeniyle) kronolojik olarak eşdeğerdir.
    `prev_hash`/`row_hash` bilerek DIŞLANIR — bütünlük içseldir, okuyucuya açılmaz.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def list(self, *, cursor: str | None, limit: int) -> dict:
        stmt = select(PlatformAuditLog).order_by(PlatformAuditLog.id.desc()).limit(limit + 1)
        if cursor:
            cursor_id = _parse_audit_cursor(cursor)
            stmt = stmt.where(PlatformAuditLog.id < cursor_id)
        rows = self._session.execute(stmt).scalars().all()
        has_more = len(rows) > limit
        page = rows[:limit]

        items = [
            {
                "id": row.id,
                "action": row.action,
                "actor_platform_admin_id": row.actor_platform_admin_id,
                "actor_email_snapshot": row.actor_email_snapshot,
                "target_org_id": row.target_org_id,
                "target_type": row.target_type,
                "target_id": row.target_id,
                "reason": row.reason,
                "result_row_count": row.result_row_count,
                "meta": row.meta,
                "ip": row.ip,
                "request_id": row.request_id,
                "created_at": row.created_at,
            }
            for row in page
        ]

        next_cursor = _encode_audit_cursor(page[-1].id) if has_more and page else None
        return {"items": items, "next_cursor": next_cursor}


_IMPERSONATION_TTL = timedelta(minutes=30)


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_aware_utc(dt: datetime) -> datetime:
    """sqlite `DateTime(timezone=True)` tzinfo'yu round-trip'te atar; naive değeri UTC say."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


class ImpersonationRepository:
    """Impersonation session yaşam döngüsü — start/approve/end. Kiracı verisi OKUMAZ/YAZMAZ.

    Fail-closed: `.start()` session insert'i ile `write_audit(...)` AYNI transaction'da —
    `write_audit` flush+commit eder (bkz. `admin_api.audit`); commit başarısız olursa
    henüz commit edilmemiş session insert'i de rollback olur (hiçbir zaman audit'siz
    session commit edilmez).
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def start(
        self, actor, target_org_id: uuid.UUID, reason: str, scope: str
    ) -> ImpersonationSession:
        row = ImpersonationSession(
            platform_admin_id=uuid.UUID(str(actor.admin_id)),
            target_org_id=target_org_id,
            reason=reason,
            scope=scope,
            requires_dual_control=(scope == "ozel_nitelikli"),
            bound_sub=actor.token_sub,
            expires_at=utc_now() + _IMPERSONATION_TTL,
        )
        self._session.add(row)
        self._session.flush()  # row.id lazım (audit meta) — henüz COMMIT edilmedi
        write_audit(
            self._session,
            actor=actor,
            action="impersonation.started",
            reason=reason,
            target_org_id=target_org_id,
            target_type="impersonation_session",
            target_id=str(row.id),
            meta={"session_id": str(row.id), "scope": scope},
        )  # write_audit COMMIT eder — session insert'i de bu commit'e dahil
        return row

    def approve(self, actor, session_id: uuid.UUID) -> ImpersonationSession:
        row = self._session.get(ImpersonationSession, session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="not_found")
        if not row.requires_dual_control:
            raise HTTPException(status_code=400, detail="dual_control_not_required")
        if row.approved_by is not None:
            raise HTTPException(status_code=409, detail="already_approved")
        if row.ended_at is not None or as_aware_utc(row.expires_at) <= utc_now():
            raise HTTPException(status_code=403, detail="session_not_active")
        if str(actor.admin_id) == str(row.platform_admin_id):
            raise HTTPException(status_code=403, detail="self_approval_forbidden")
        row.approved_by = uuid.UUID(str(actor.admin_id))
        self._session.flush()
        write_audit(
            self._session,
            actor=actor,
            action="impersonation.approved",
            reason=row.reason,
            target_org_id=row.target_org_id,
            target_type="impersonation_session",
            target_id=str(row.id),
            meta={"session_id": str(row.id)},
        )
        return row

    def end(self, actor, session_id: uuid.UUID) -> ImpersonationSession:
        row = self._session.get(ImpersonationSession, session_id)
        if row is None:
            raise HTTPException(status_code=404, detail="not_found")
        if row.ended_at is not None:
            raise HTTPException(status_code=409, detail="already_ended")
        row.ended_at = utc_now()
        row.end_kind = "manual"
        self._session.flush()
        write_audit(
            self._session,
            actor=actor,
            action="impersonation.ended",
            reason=row.reason,
            target_org_id=row.target_org_id,
            target_type="impersonation_session",
            target_id=str(row.id),
            meta={"session_id": str(row.id)},
        )
        return row


def resolve_active_session(
    session: Session, admin, session_id: uuid.UUID, token_sub: str
) -> ImpersonationSession:
    """Task 9'un kapsamlı okuma proxy'sinin dayanacağı tek kapı — ALL şartlar tutmalı, yoksa 403.

    Sahiplik bağı + süre + sub-bağ + dual-control onayı + owner admin'in HÂLÂ aktif olduğunun
    taze DB okuması (mid-session deprovision'ı yakalar — `require_platform_admin` istek başına
    zaten kontrol eder, bu savunma derinliği).
    """
    row = session.get(ImpersonationSession, session_id)
    if row is None:
        raise HTTPException(status_code=403, detail="impersonation_session_invalid")

    owner_active = session.execute(
        select(PlatformAdmin.is_active).where(PlatformAdmin.id == row.platform_admin_id)
    ).scalar_one_or_none()

    valid = (
        str(row.platform_admin_id) == str(admin.admin_id)
        and row.ended_at is None
        and as_aware_utc(row.expires_at) > utc_now()
        and row.bound_sub == token_sub
        and (not row.requires_dual_control or row.approved_by is not None)
        and bool(owner_active)
    )
    if not valid:
        raise HTTPException(status_code=403, detail="impersonation_session_invalid")
    return row
