"""Denetim izi okuma API'si (KVKK m.12) — yönetici-only, org-kapsamlı, imleç sayfalama."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from ..auth.identity import Identity, require_role
from ..auth.tenant_session import tenant_session
from ..repositories import AuditLogRepository

router = APIRouter(prefix="/api/audit", tags=["audit"])

_MAX_LIMIT = 200


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class AuditItem(_Camel):
    id: uuid.UUID
    created_at: datetime
    action: str
    actor_email: str
    target_type: str | None
    target_id: str | None
    ip: str | None
    request_id: str | None
    meta: dict | None


class AuditPage(_Camel):
    items: list[AuditItem]
    next_cursor: str | None


def _parse_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        created_at_raw, id_raw = cursor.rsplit("|", 1)
        return datetime.fromisoformat(created_at_raw), uuid.UUID(id_raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Geçersiz cursor.") from exc


@router.get("", response_model=AuditPage)
def list_audit(
    limit: int = Query(50, ge=1, le=_MAX_LIMIT),
    before: str | None = None,
    action: str | None = None,
    identity: Identity = Depends(require_role("yonetici")),
    session: Session = Depends(tenant_session),
) -> AuditPage:
    effective_limit = min(limit, _MAX_LIMIT)
    before_cursor = _parse_cursor(before) if before else None
    rows = AuditLogRepository(session).list(
        identity.org_id, limit=effective_limit, before=before_cursor, action=action
    )
    has_more = len(rows) > effective_limit
    page_rows = rows[:effective_limit]

    items = [
        AuditItem(
            id=log.id,
            created_at=log.created_at,
            action=log.action,
            actor_email=email or "—",
            target_type=log.target_type,
            target_id=log.target_id,
            ip=log.ip,
            request_id=log.request_id,
            meta=log.meta,
        )
        for log, email in page_rows
    ]

    next_cursor = None
    if has_more and page_rows:
        last_log, _ = page_rows[-1]
        next_cursor = f"{last_log.created_at.isoformat()}|{last_log.id}"

    return AuditPage(items=items, next_cursor=next_cursor)
