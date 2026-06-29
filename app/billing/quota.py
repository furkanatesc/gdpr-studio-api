"""Kota + maliyet enforcement + kullanım/maliyet sayımı (generate uçları için)."""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..auth.identity import Identity, get_current_identity
from ..auth.tenant_session import tenant_session
from ..config import Settings, get_settings
from .entitlement import current_period, resolve_entitlement
from .pricing import cost_budget_for, cost_micros
from .repositories import UsageRepository


def enforce_generation_quota(
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(tenant_session),
    x_anthropic_key: str | None = Header(default=None, alias="X-Anthropic-Key"),
) -> Identity:
    """Üretimden ÖNCE: (1) ücretsiz doküman tavanı; (2) managed maliyet bütçesi.

    tenant_session org RLS bağlamını set eder. BYOK (X-Anthropic-Key) → maliyet
    kontrolü atlanır (bizim maliyetimiz değil); doküman tavanı yine uygulanır.
    """
    settings = get_settings()
    if not settings.billing_enabled:
        return identity  # dev/billing-kapalı: enforcement yok
    ent = resolve_entitlement(session, identity.org_id)
    # (1) Ücretsiz doküman tavanı
    if ent.quota is not None and ent.used >= ent.quota:
        raise HTTPException(
            status_code=402,
            detail={"code": "quota_exceeded", "plan": ent.plan, "used": ent.used, "quota": ent.quota},
        )
    # (2) Managed maliyet bütçesi (BYOK hariç)
    if x_anthropic_key is None:
        budget = cost_budget_for(ent.plan)
        if budget is not None:
            used_cost = UsageRepository(session).get_cost(identity.org_id, current_period())
            if used_cost >= budget:
                raise HTTPException(
                    status_code=402,
                    detail={
                        "code": "cost_budget_exceeded",
                        "plan": ent.plan,
                        "usedUsd": round(used_cost / 1_000_000, 2),
                        "budgetUsd": round(budget / 1_000_000, 2),
                    },
                )
    return identity


def record_generation_usage(
    session: Session,
    settings: Settings,
    org_id: uuid.UUID,
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    byok: bool,
) -> None:
    """Üretimden SONRA (yalnız başarıda): doküman sayacı + (managed ise) maliyet birikimi + commit."""
    if not settings.billing_enabled:
        return
    repo = UsageRepository(session)
    repo.increment(org_id, current_period())  # doküman sayımı (BYOK dahil — mevcut davranış)
    if not byok:
        cm = cost_micros(model, input_tokens, output_tokens)
        repo.add_cost(org_id, current_period(), input_tokens, output_tokens, cm)
    session.commit()
