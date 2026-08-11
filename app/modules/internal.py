"""İç/operasyonel uçlar — korumalı (X-Internal-Token). Retention sweep + org ops (H3)."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..auth.tenant_session import begin_provisioning, end_provisioning
from ..config import get_settings
from ..db import get_session
from ..models import Organization
from ..retention import retention_sweep
from ..supabase_admin import delete_supabase_user

router = APIRouter(prefix="/api/internal", tags=["internal"])


def _require_internal_token(request: Request) -> None:
    settings = get_settings()
    token = request.headers.get("X-Internal-Token", "")
    # Token yapılandırılmamışsa uç tamamen kapalı (fail-closed).
    if not settings.internal_api_token or token != settings.internal_api_token:
        raise HTTPException(status_code=403, detail="Yetkisiz.")


@router.post("/purge")
def run_sweep(request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_internal_token(request)
    settings = get_settings()
    return retention_sweep(
        session,
        invite_retention_days=settings.invite_retention_days,
        org_grace_days=settings.dsar_purge_grace_days,
        supabase_delete=delete_supabase_user,
    )


def _set_org_status(session: Session, org_id: uuid.UUID, *, expect: str, new: str, action: str) -> dict[str, Any]:
    begin_provisioning(session)
    try:
        org = session.get(Organization, org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Kurum bulunamadı.")
        if org.status != expect:
            raise HTTPException(status_code=409, detail=f"Kurum '{org.status}' durumunda; işlem geçersiz.")
        org.status = new
        record_audit(session, org_id=org_id, action=action,
                     target_type="organization", target_id=str(org_id))
        session.commit()
    finally:
        end_provisioning(session)
    return {"orgId": str(org_id), "status": new}


@router.post("/orgs/{org_id}/suspend")
def suspend_org(org_id: uuid.UUID, request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_internal_token(request)
    return _set_org_status(session, org_id, expect="active", new="suspended", action="org.suspended")


@router.post("/orgs/{org_id}/reactivate")
def reactivate_org(org_id: uuid.UUID, request: Request, session: Session = Depends(get_session)) -> dict[str, Any]:
    _require_internal_token(request)
    return _set_org_status(session, org_id, expect="suspended", new="active", action="org.reactivated")
