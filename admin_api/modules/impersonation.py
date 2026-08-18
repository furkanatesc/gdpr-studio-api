"""Impersonation session yaşam döngüsü — H5_LEGAL_READY kapısı + dual-control + fail-closed audit.

Yaşam döngüsü SADECE: start/approve/end + `resolve_active_session`. Kapsamlı kiracı okuma
proxy'si (bypass-off assert, erişim-başı audit, hacim sınırı) Task 9'da AYRI bir uçtur —
burada `set_org_context`/`begin_provisioning` YOK, tenant verisi okunmaz.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from app.models import ImpersonationSession

from ..auth import PlatformAdminIdentity, require_platform_admin
from ..config import get_admin_settings
from ..db import admin_session
from ..repositories import ImpersonationRepository
from ..repositories import resolve_active_session as resolve_active_session

router = APIRouter(prefix="/admin/impersonation", tags=["admin-impersonation"])

__all__ = ["router", "resolve_active_session"]


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ImpersonationStartRequest(_Camel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    target_org_id: uuid.UUID
    reason: str
    scope: str


class ImpersonationSessionResponse(_Camel):
    id: uuid.UUID
    platform_admin_id: uuid.UUID
    target_org_id: uuid.UUID
    reason: str
    scope: str
    requires_dual_control: bool
    approved_by: uuid.UUID | None
    bound_sub: str
    started_at: datetime
    expires_at: datetime
    ended_at: datetime | None
    end_kind: str | None

    @classmethod
    def from_row(cls, row: ImpersonationSession) -> ImpersonationSessionResponse:
        return cls(
            id=row.id,
            platform_admin_id=row.platform_admin_id,
            target_org_id=row.target_org_id,
            reason=row.reason,
            scope=row.scope,
            requires_dual_control=row.requires_dual_control,
            approved_by=row.approved_by,
            bound_sub=row.bound_sub,
            started_at=row.started_at,
            expires_at=row.expires_at,
            ended_at=row.ended_at,
            end_kind=row.end_kind,
        )


@router.post("", response_model=ImpersonationSessionResponse, status_code=201)
def start_impersonation(
    body: ImpersonationStartRequest,
    identity: PlatformAdminIdentity = Depends(require_platform_admin),
    session: Session = Depends(admin_session),
) -> ImpersonationSessionResponse:
    if not get_admin_settings().h5_legal_ready:
        raise HTTPException(status_code=403, detail="h5_legal_not_ready")
    row = ImpersonationRepository(session).start(
        identity, body.target_org_id, body.reason, body.scope
    )
    return ImpersonationSessionResponse.from_row(row)


@router.post("/{session_id}/approve", response_model=ImpersonationSessionResponse)
def approve_impersonation(
    session_id: uuid.UUID,
    identity: PlatformAdminIdentity = Depends(require_platform_admin),
    session: Session = Depends(admin_session),
) -> ImpersonationSessionResponse:
    row = ImpersonationRepository(session).approve(identity, session_id)
    return ImpersonationSessionResponse.from_row(row)


@router.delete("/{session_id}", response_model=ImpersonationSessionResponse)
def end_impersonation(
    session_id: uuid.UUID,
    identity: PlatformAdminIdentity = Depends(require_platform_admin),
    session: Session = Depends(admin_session),
) -> ImpersonationSessionResponse:
    row = ImpersonationRepository(session).end(identity, session_id)
    return ImpersonationSessionResponse.from_row(row)
