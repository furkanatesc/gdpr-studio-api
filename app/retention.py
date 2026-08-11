"""Retention (H3-3) — davet + audit süpürme, birleşik sweep.

Davet/org purge kvkk_app-güvenli; audit purge YALNIZ owner rolle (REVOKE DELETE).
Purge fonksiyonları cross-org → begin_provisioning ile FORCE-RLS bypass edilir.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, delete, or_
from sqlalchemy.orm import Session

from .auth.tenant_session import begin_provisioning, end_provisioning
from .dsar_purge import purge_expired_orgs
from .models import AuditLog, Invitation


def purge_terminal_invitations(
    session: Session, *, retention_days: int, now: datetime | None = None
) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=retention_days)
    begin_provisioning(session)
    try:
        result = session.execute(
            delete(Invitation).where(
                Invitation.created_at < cutoff,
                or_(
                    Invitation.status.in_(("accepted", "revoked")),
                    and_(Invitation.status == "pending", Invitation.expires_at < now),
                ),
            )
        )
        session.commit()
    finally:
        end_provisioning(session)
    return {"invitationsPurged": result.rowcount or 0}


def purge_audit_logs(
    session: Session, *, retention_days: int, now: datetime | None = None
) -> dict[str, Any]:
    if retention_days <= 0:
        return {"auditLogsPurged": 0}
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=retention_days)
    begin_provisioning(session)
    try:
        result = session.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
        session.commit()
    finally:
        end_provisioning(session)
    return {"auditLogsPurged": result.rowcount or 0}


def retention_sweep(
    session: Session, *, invite_retention_days: int, org_grace_days: int,
    supabase_delete=None,
) -> dict[str, Any]:
    inv = purge_terminal_invitations(session, retention_days=invite_retention_days)
    org = purge_expired_orgs(session, grace_days=org_grace_days, supabase_delete=supabase_delete)
    return {
        "invitationsPurged": inv["invitationsPurged"],
        "orgsPurged": org["count"],
        "purged": org["purged"],
    }
