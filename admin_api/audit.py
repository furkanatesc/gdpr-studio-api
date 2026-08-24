"""Hash-zincirli, fail-closed platform-admin denetim yazıcısı.

`app/modules/ihlal.py:262`'deki best-effort (yut-ve-devam) desenin TERSİ: burada
`write_audit` flush+commit başarısız olursa RAISE eder — çağıran devam ETMEMELİDİR.
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.models import PlatformAuditLog

from .request_context import get_admin_client_ip


def _as_uuid(value) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _hash(prev: str | None, payload: dict) -> str:
    return hashlib.sha256(
        ((prev or "") + json.dumps(payload, sort_keys=True, default=str)).encode()
    ).hexdigest()


def _payload(
    *,
    actor_id,
    action,
    reason,
    target_org_id,
    target_type,
    target_id,
    result_row_count,
    meta,
    created_at,
    ip,
    request_id,
    actor_email_snapshot,
) -> dict:
    """The exact field set the row_hash covers. `created_at`, `ip`, `request_id` and
    `actor_email_snapshot` are hashed too so an owner with UPDATE cannot silently rewrite
    the when/where/who of a row without invalidating the chain."""
    return {
        "actor": str(actor_id) if actor_id is not None else None,
        "actor_email_snapshot": actor_email_snapshot,
        "action": action,
        "reason": reason,
        "target_org_id": str(target_org_id) if target_org_id is not None else None,
        "target_type": target_type,
        "target_id": target_id,
        "result_row_count": result_row_count,
        "meta": meta,
        "created_at": created_at.isoformat() if created_at is not None else None,
        "ip": ip,
        "request_id": request_id,
    }


def recompute_row_hash(row: PlatformAuditLog) -> str:
    """WORM verification: recompute a stored row's hash from its own fields to detect
    tampering. Any post-write mutation of a hashed field makes this diverge from row.row_hash."""
    return _hash(
        row.prev_hash,
        _payload(
            actor_id=row.actor_platform_admin_id,
            action=row.action,
            reason=row.reason,
            target_org_id=row.target_org_id,
            target_type=row.target_type,
            target_id=row.target_id,
            result_row_count=row.result_row_count,
            meta=row.meta,
            created_at=row.created_at,
            ip=row.ip,
            request_id=row.request_id,
            actor_email_snapshot=row.actor_email_snapshot,
        ),
    )


def write_audit(
    session,
    *,
    actor,
    action,
    reason,
    target_org_id=None,
    target_type=None,
    target_id=None,
    result_row_count=None,
    meta=None,
    ip=None,
    request_id=None,
) -> PlatformAuditLog:
    if ip is None:
        ip = get_admin_client_ip()  # trusted-hop socket peer, stamped by AdminRateLimitMiddleware
    prev_stmt = select(PlatformAuditLog.row_hash).order_by(PlatformAuditLog.id.desc()).limit(1)
    if session.bind.dialect.name == "postgresql":
        # Serialize concurrent appends: without FOR UPDATE, two writers can both read the
        # same prev_hash and fork the chain. sqlite has no row locking (and is single-writer
        # by nature), so the plain select is used there.
        prev_stmt = prev_stmt.with_for_update()
    prev = session.execute(prev_stmt).scalar()
    # Stamp created_at in Python (not the DB server_default) so it is known at hash time
    # and therefore covered by row_hash. Always UTC.
    created_at = datetime.now(UTC)
    actor_email_snapshot = getattr(actor, "email", None)
    payload = _payload(
        actor_id=getattr(actor, "admin_id", None),
        action=action,
        reason=reason,
        target_org_id=target_org_id,
        target_type=target_type,
        target_id=target_id,
        result_row_count=result_row_count,
        meta=meta,
        created_at=created_at,
        ip=ip,
        request_id=request_id,
        actor_email_snapshot=actor_email_snapshot,
    )
    row = PlatformAuditLog(
        actor_platform_admin_id=_as_uuid(getattr(actor, "admin_id", None)),
        actor_email_snapshot=actor_email_snapshot,
        action=action,
        reason=reason,
        target_org_id=_as_uuid(target_org_id),
        target_type=target_type,
        target_id=target_id,
        result_row_count=result_row_count,
        meta=meta,
        ip=ip,
        request_id=request_id,
        created_at=created_at,
        prev_hash=prev,
        row_hash=_hash(prev, payload),
    )
    session.add(row)
    session.flush()
    session.commit()  # fail-closed: hata durumunda exception yükselir, çağıran YAKALAMAMALI/yutmamalı
    return row
