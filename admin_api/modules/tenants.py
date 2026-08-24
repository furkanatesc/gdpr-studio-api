"""Kiracı listesi + tek-kiracı detay uçları — platform admin.

Liste: rollup + küçük indeksli join (organizations/subscriptions) — cross-tenant
generated_documents/usage_counters/client_documents TARAMASI YOK. Detay: tek-org
canlı okuma, `set_org_context` ile (bkz. repositories.TenantAdminRepository).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from ..auth import PlatformAdminIdentity, require_platform_admin
from ..db import admin_session
from ..repositories import TenantAdminRepository

router = APIRouter(prefix="/admin/tenants", tags=["admin-tenants"])

_MAX_LIMIT = 200


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class TenantSummary(_Camel):
    id: uuid.UUID
    name: str
    sector: str | None
    status: str
    created_at: datetime
    plan: str | None
    subscription_status: str | None


class TenantListPage(_Camel):
    items: list[TenantSummary]
    next_cursor: str | None


class UsageSummary(_Camel):
    period: str
    doc_count: int
    cost_micros: int
    input_tokens: int
    output_tokens: int


class TenantDetailResponse(_Camel):
    id: uuid.UUID
    name: str
    sector: str | None
    status: str
    created_at: datetime
    plan: str | None
    subscription_status: str | None
    current_period_end: datetime | None
    member_count: int
    usage: UsageSummary | None


@router.get("", response_model=TenantListPage)
def list_tenants(
    cursor: str | None = None,
    q: str | None = None,
    status: str | None = None,
    limit: int = Query(50, ge=1, le=_MAX_LIMIT),
    identity: PlatformAdminIdentity = Depends(require_platform_admin),
    session: Session = Depends(admin_session),
) -> TenantListPage:
    try:
        page = TenantAdminRepository(session).list(cursor=cursor, q=q, status=status, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Geçersiz cursor.") from exc
    return TenantListPage(
        items=[TenantSummary(**item) for item in page["items"]],
        next_cursor=page["next_cursor"],
    )


@router.get("/{org_id}", response_model=TenantDetailResponse)
def get_tenant_detail(
    org_id: uuid.UUID,
    identity: PlatformAdminIdentity = Depends(require_platform_admin),
    session: Session = Depends(admin_session),
) -> TenantDetailResponse:
    detail = TenantAdminRepository(session).detail(org_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Kiracı bulunamadı.")
    usage = detail.pop("usage")
    return TenantDetailResponse(**detail, usage=UsageSummary(**usage) if usage else None)
