"""Billing uçları — checkout / portal / status (webhook A6'da eklenir)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..auth.identity import Identity, get_current_identity, require_role
from ..auth.tenant_session import begin_provisioning, end_provisioning, tenant_session
from ..billing import stripe_client
from ..billing.entitlement import resolve_entitlement
from ..billing.repositories import StripeEventRepository, SubscriptionRepository
from ..config import get_settings
from ..db import get_session

router = APIRouter(prefix="/api/billing", tags=["billing"])

_PLANS = {"standart", "premium"}
_INTERVALS = {"month", "year"}


class CheckoutRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

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


def _status_map(stripe_status: str) -> str:
    if stripe_status in ("active", "trialing"):
        return "active"
    if stripe_status in ("past_due", "unpaid"):
        return "past_due"
    if stripe_status in ("canceled", "incomplete_expired"):
        return "canceled"
    # Bilinmeyen/gelecekteki Stripe durumları kısıtlayıcı yönde eşleşir → ücretsiz kota.
    return "canceled"


def _handle_event(session, settings, event: dict) -> None:
    etype = event["type"]
    obj = event["data"]["object"]
    subs = SubscriptionRepository(session)

    if etype == "checkout.session.completed":
        org_id = obj.get("client_reference_id")
        if org_id:
            subs.upsert(
                uuid.UUID(org_id),
                customer_id=obj.get("customer"),
                subscription_id=obj.get("subscription"),
            )
    elif etype in ("customer.subscription.created", "customer.subscription.updated"):
        org_id = (obj.get("metadata") or {}).get("org_id")
        if not org_id:
            return  # org bağlanmamış → güvenli no-op (sıra-dışı event toleransı)
        price_id = obj["items"]["data"][0]["price"]["id"]
        mapped = settings.price_map.get(price_id)
        period_end = obj.get("current_period_end")
        subs.upsert(
            uuid.UUID(org_id),
            customer_id=obj.get("customer"),
            subscription_id=obj.get("id"),
            plan=mapped[0] if mapped else None,
            interval=mapped[1] if mapped else None,
            status=_status_map(obj.get("status", "active")),
            current_period_end=datetime.fromtimestamp(period_end, UTC) if period_end else None,
        )
    elif etype == "customer.subscription.deleted":
        org_id = (obj.get("metadata") or {}).get("org_id")
        if org_id:
            subs.upsert(uuid.UUID(org_id), plan="baslangic", status="canceled", interval=None)
    elif etype == "invoice.payment_failed":
        customer_id = obj.get("customer")
        if customer_id:
            subs.set_status_by_customer(customer_id, "past_due")
    # bilinmeyen olaylar: sessizce yoksay (idempotency kaydı yine de tutulur)


@router.post("/webhook")
async def webhook(request: Request, session: Session = Depends(get_session)) -> dict:
    settings = get_settings()
    if not settings.billing_enabled:
        raise HTTPException(status_code=503, detail="Faturalandırma şu an kullanılamıyor.")
    payload = await request.body()
    sig = request.headers.get("Stripe-Signature", "")
    try:
        event = stripe_client.construct_event(settings, payload, sig)
    except Exception:
        raise HTTPException(status_code=400, detail="Geçersiz webhook imzası.") from None

    # Güvenilen sunucu-sunucu yolu: tüm handler bypass-RLS bağlamında (commit'te sıfırlanır).
    begin_provisioning(session)
    try:
        events = StripeEventRepository(session)
        if events.seen(event["id"]):
            session.commit()
            return {"status": "duplicate"}
        _handle_event(session, settings, event)
        events.record(event["id"], event["type"])
        session.commit()
    finally:
        end_provisioning(session)
    return {"status": "ok"}
