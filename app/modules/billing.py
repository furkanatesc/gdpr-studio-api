"""Billing uçları — checkout / portal / status (webhook A6'da eklenir)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..auth.identity import Identity, get_current_identity, require_role
from ..auth.tenant_session import tenant_session
from ..billing import stripe_client
from ..billing.entitlement import resolve_entitlement
from ..billing.repositories import SubscriptionRepository
from ..config import get_settings

router = APIRouter(prefix="/api/billing", tags=["billing"])

_PLANS = {"standart", "premium"}
_INTERVALS = {"month", "year"}


class CheckoutRequest(BaseModel):
    plan: str
    interval: str


class UrlOut(BaseModel):
    url: str


class UsageOut(BaseModel):
    used: int
    quota: int | None


class BillingStatusOut(BaseModel):
    plan: str
    status: str
    interval: str | None
    currentPeriodEnd: datetime | None
    usage: UsageOut
    canManage: bool


@router.get("/status", response_model=BillingStatusOut)
def status(
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(tenant_session),
) -> BillingStatusOut:
    ent = resolve_entitlement(session, identity.org_id)
    return BillingStatusOut(
        plan=ent.plan,
        status=ent.status,
        interval=ent.interval,
        currentPeriodEnd=ent.current_period_end,
        usage=UsageOut(used=ent.used, quota=ent.quota),
        canManage=identity.role == "yonetici",
    )


@router.post("/checkout", response_model=UrlOut)
def checkout(
    body: CheckoutRequest,
    identity: Identity = Depends(require_role("yonetici")),
    session: Session = Depends(tenant_session),
) -> UrlOut:
    settings = get_settings()
    if not settings.billing_enabled:
        raise HTTPException(status_code=503, detail="Faturalandırma şu an kullanılamıyor.")
    if body.plan not in _PLANS or body.interval not in _INTERVALS:
        raise HTTPException(status_code=422, detail="Geçersiz plan veya periyot.")
    price_id = settings.price_for(body.plan, body.interval)
    if not price_id:
        raise HTTPException(status_code=503, detail="Bu plan için fiyat tanımlı değil.")
    sub = SubscriptionRepository(session).get_by_org(identity.org_id)
    url = stripe_client.create_checkout_session(
        settings,
        price_id=price_id,
        org_id=str(identity.org_id),
        customer_id=sub.stripe_customer_id if sub else None,
        success_url=settings.billing_success_url,
        cancel_url=settings.billing_cancel_url,
    )
    return UrlOut(url=url)


@router.post("/portal", response_model=UrlOut)
def portal(
    identity: Identity = Depends(require_role("yonetici")),
    session: Session = Depends(tenant_session),
) -> UrlOut:
    settings = get_settings()
    if not settings.billing_enabled:
        raise HTTPException(status_code=503, detail="Faturalandırma şu an kullanılamıyor.")
    sub = SubscriptionRepository(session).get_by_org(identity.org_id)
    if sub is None or not sub.stripe_customer_id:
        raise HTTPException(status_code=409, detail="Henüz bir aboneliğiniz yok.")
    url = stripe_client.create_portal_session(
        settings, customer_id=sub.stripe_customer_id, return_url=settings.billing_success_url
    )
    return UrlOut(url=url)
