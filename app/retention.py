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
from .models import Invitation


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
