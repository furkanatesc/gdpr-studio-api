"""Hash-zincirli, fail-closed platform-admin denetim yazıcısı.

`app/modules/ihlal.py:262`'deki best-effort (yut-ve-devam) desenin TERSİ: burada
`write_audit` flush+commit başarısız olursa RAISE eder — çağıran devam ETMEMELİDİR.
"""

import hashlib
import json
import uuid

from sqlalchemy import select

from app.models import PlatformAuditLog


def _as_uuid(value) -> uuid.UUID | None:
    if value is None or isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def _hash(prev: str | None, payload: dict) -> str:
    return hashlib.sha256(
        ((prev or "") + json.dumps(payload, sort_keys=True, default=str)).encode()
    ).hexdigest()


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
    prev_stmt = select(PlatformAuditLog.row_hash).order_by(PlatformAuditLog.id.desc()).limit(1)
    if session.bind.dialect.name == "postgresql":
        # Serialize concurrent appends: without FOR UPDATE, two writers can both read the
        # same prev_hash and fork the chain. sqlite has no row locking (and is single-writer
        # by nature), so the plain select is used there.
        prev_stmt = prev_stmt.with_for_update()
    prev = session.execute(prev_stmt).scalar()
    payload = {
        "actor": getattr(actor, "admin_id", None),
        "action": action,
        "reason": reason,
        "target_org_id": str(target_org_id) if target_org_id is not None else None,
        "target_type": target_type,
        "target_id": target_id,
        "result_row_count": result_row_count,
        "meta": meta,
    }
    row = PlatformAuditLog(
        actor_platform_admin_id=_as_uuid(getattr(actor, "admin_id", None)),
        actor_email_snapshot=getattr(actor, "email", None),
        action=action,
        reason=reason,
        target_org_id=_as_uuid(target_org_id),
        target_type=target_type,
        target_id=target_id,
        result_row_count=result_row_count,
        meta=meta,
        ip=ip,
        request_id=request_id,
        prev_hash=prev,
        row_hash=_hash(prev, payload),
    )
    session.add(row)
    session.flush()
    session.commit()  # fail-closed: hata durumunda exception yükselir, çağıran YAKALAMAMALI/yutmamalı
    return row
