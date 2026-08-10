"""İç/operasyonel uçlar — korumalı (X-Internal-Token). DSAR purge tetiği (H3-2 Part 2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_session
from ..dsar_purge import purge_expired_orgs
from ..supabase_admin import delete_supabase_user

router = APIRouter(prefix="/api/internal", tags=["internal"])


def _require_internal_token(request: Request) -> None:
    settings = get_settings()
    token = request.headers.get("X-Internal-Token", "")
    # Token yapılandırılmamışsa uç tamamen kapalı (fail-closed).
    if not settings.internal_api_token or token != settings.internal_api_token:
        raise HTTPException(status_code=403, detail="Yetkisiz.")


@router.post("/purge")
def run_purge(
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    _require_internal_token(request)
    settings = get_settings()
    result = purge_expired_orgs(
        session,
        grace_days=settings.dsar_purge_grace_days,
        supabase_delete=delete_supabase_user,
    )
    session.commit()
    return result
