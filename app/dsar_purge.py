"""DSAR (H3-2 Part 2) — gecikmeli purge: soft-delete'ten `grace_days` sonra kalıcı silme.

FK-güvenli sıra: ON DELETE CASCADE'i OLMAYAN org tabloları açıkça silinir; sonra üyeliği
kalkan users; sonra org satırı silinir → ON DELETE CASCADE ile clients/client_documents(
+versions)/client_processors/processes(org)/**audit_logs** gider. audit_logs append-only
(kvkk_app'te REVOKE UPDATE,DELETE) → doğrudan silinemez AMA org-satırı silmedeki FK-CASCADE
aksiyonu privilege/RLS'i bypass eder → otomatik gider.

Cross-org işlem olduğundan begin_provisioning (bypass RLS) altında koşar. Supabase auth
silme env-gated + best-effort (purge'i bloke etmez).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .auth.tenant_session import begin_provisioning, end_provisioning
from .models import (
    Client,
    ClientDocument,
    ClientDocumentVersion,
    ClientProcessor,
    ComplianceStatus,
    GeneratedDocument,
    Invitation,
    Membership,
    Organization,
    Process,
    Subscription,
    UsageCounter,
    User,
)

_log = logging.getLogger("app.dsar")

# ON DELETE CASCADE'i OLMAYAN (RESTRICT) org tabloları — org satırından ÖNCE açık silinmeli.
# clients/client_documents/versions/processors/processes/audit_logs CASCADE → org satırı silince gider.
_RESTRICT_TABLES = [
    UsageCounter,
    ComplianceStatus,
    GeneratedDocument,
    Invitation,
    Membership,
    Subscription,
]
# CASCADE tabloları da (audit_logs HARİÇ) açıkça silinir → sqlite (FK-cascade yok) + prod tutarlı.
# audit_logs YALNIZ org-satırı CASCADE ile gider (REVOKE DELETE → açık silinemez).
_CASCADE_TABLES_EXPLICIT = [
    ClientDocumentVersion,
    ClientDocument,
    ClientProcessor,
    Client,
    Process,
]


def purge_expired_orgs(
    session: Session,
    *,
    grace_days: int,
    now: datetime | None = None,
    supabase_delete: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Süresi dolmuş (status='deleting', deleted_at < now-grace) org'ları kalıcı siler."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=grace_days)

    begin_provisioning(session)
    try:
        expired = list(
            session.scalars(
                select(Organization).where(
                    Organization.status == "deleting",
                    Organization.deleted_at.is_not(None),
                    Organization.deleted_at < cutoff,
                )
            )
        )
        purged: list[dict[str, Any]] = []
        for org in expired:
            members = list(
                session.scalars(
                    select(User)
                    .join(Membership, Membership.user_id == User.id)
                    .where(Membership.org_id == org.id)
                )
            )

            for model in (*_RESTRICT_TABLES, *_CASCADE_TABLES_EXPLICIT):
                session.execute(delete(model).where(model.org_id == org.id))

            # Üyeliği tamamen kalkan (başka org'da olmayan) kullanıcıları sil → orphan.
            orphan_supabase_ids: list[str] = []
            for u in members:
                remaining = session.scalar(
                    select(func.count()).select_from(Membership).where(Membership.user_id == u.id)
                )
                if not remaining:
                    orphan_supabase_ids.append(u.supabase_user_id)
                    session.execute(delete(User).where(User.id == u.id))

            # Org satırı → CASCADE ile audit_logs (+ kalan cascade tablolar) gider.
            session.execute(delete(Organization).where(Organization.id == org.id))

            # Supabase auth silme (env-gated, best-effort — DB silmeyi bloke etmez).
            supabase_deleted = 0
            if supabase_delete is not None:
                for sup in orphan_supabase_ids:
                    try:
                        if supabase_delete(sup):
                            supabase_deleted += 1
                    except Exception:
                        _log.exception("supabase auth silme hata (user=%s)", sup)

            purged.append(
                {
                    "orgId": str(org.id),
                    "orphanUsers": len(orphan_supabase_ids),
                    "supabaseDeleted": supabase_deleted,
                }
            )

        session.commit()
    finally:
        end_provisioning(session)

    if purged:
        _log.info("dsar purge: %d org kalıcı silindi", len(purged))
    return {"count": len(purged), "purged": purged}
