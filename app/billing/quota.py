"""Kota enforcement + kullanım sayımı (generate uçları için)."""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from ..auth.identity import Identity, get_current_identity
from ..auth.tenant_session import tenant_session
from ..config import Settings, get_settings
from .entitlement import current_period, resolve_entitlement
from .repositories import UsageRepository


def enforce_generation_quota(
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(tenant_session),
) -> Identity:
    """Üretimden ÖNCE: ücretsiz plan tavanı dolduysa 402. tenant_session org RLS bağlamını set eder."""
    settings = get_settings()
    if not settings.billing_enabled:
        return identity  # dev/billing-kapalı: enforcement yok
    ent = resolve_entitlement(session, identity.org_id)
    if ent.quota is not None and ent.used >= ent.quota:
        raise HTTPException(
            status_code=402,
            detail={"code": "quota_exceeded", "plan": ent.plan, "used": ent.used, "quota": ent.quota},
        )
    return identity


def record_generation_usage(session: Session, settings: Settings, org_id: uuid.UUID) -> None:
    """Üretimden SONRA (yalnız başarıda): mevcut periyot sayacını artır + commit."""
    if not settings.billing_enabled:
        return
    UsageRepository(session).increment(org_id, current_period())
    session.commit()
