"""Platform audit read endpoint — `id` DESC keyset pagination, integrity fields excluded.

Mirrors `modules/tenants.py`. `platform_audit_logs` has NO RLS; `kvkk_admin_ro` has a plain
SELECT grant — read directly (no `begin_provisioning`/`set_org_context`, unlike the
impersonation read proxy which is scoped to a single tenant).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from ..auth import PlatformAdminIdentity, require_platform_admin
from ..db import admin_session
from ..repositories import PlatformAuditRepository

router = APIRouter(prefix="/admin/audit", tags=["admin-audit"])

_MAX_LIMIT = 200


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AuditEntry(_Camel):
    id: int
    action: str
    actor_platform_admin_id: uuid.UUID | None
    actor_email_snapshot: str | None
    target_org_id: uuid.UUID | None
    target_type: str | None
    target_id: str | None
    reason: str
    result_row_count: int | None
    meta: dict | None
    ip: str | None
    request_id: str | None
    created_at: datetime


class AuditPage(_Camel):
    items: list[AuditEntry]
    next_cursor: str | None


@router.get("", response_model=AuditPage)
def list_audit(
    cursor: str | None = None,
    limit: int = 50,
    identity: PlatformAdminIdentity = Depends(require_platform_admin),
    session: Session = Depends(admin_session),
) -> AuditPage:
    if not (1 <= limit <= _MAX_LIMIT):
        raise HTTPException(status_code=422, detail="invalid_limit")
    try:
        page = PlatformAuditRepository(session).list(cursor=cursor, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="malformed_cursor") from exc
    return AuditPage(
        items=[AuditEntry(**item) for item in page["items"]],
        next_cursor=page["next_cursor"],
    )
