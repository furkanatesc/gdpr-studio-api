"""Stripe SDK sarmalayıcı — lazy import; CI/testlerde monkeypatch'lenir.

`_stripe()` indirection'ı testlerin gerçek SDK'yı sahte bir nesneyle değiştirmesini
sağlar (gerçek Stripe API'ye asla gidilmez). api_key her çağrıda settings'ten set edilir.
"""

from __future__ import annotations

from ..config import Settings


def _stripe():
    import stripe  # lazy: billing kapalıyken import maliyeti yok

    return stripe


def create_checkout_session(
    settings: Settings,
    *,
    price_id: str,
    org_id: str,
    customer_id: str | None,
    success_url: str,
    cancel_url: str,
) -> str:
    stripe = _stripe()
    stripe.api_key = settings.stripe_secret_key
    params: dict = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        "client_reference_id": org_id,
        "subscription_data": {"metadata": {"org_id": org_id}},
        # KDV: Price'lar KDV hariç (Dashboard'da tax_behavior=exclusive) → Stripe Tax
        # %20 KDV'yi checkout'ta ayrı satır olarak ekler. automatic_tax müşterinin
        # konumunu ister → adres toplanır; vergi no (B2B e-fatura için) opsiyonel alınır.
        "automatic_tax": {"enabled": True},
        "billing_address_collection": "required",
        "tax_id_collection": {"enabled": True},
    }
    if customer_id:
        params["customer"] = customer_id
        # Mevcut müşteri + automatic_tax: checkout'ta toplanan adresin müşteriye geri
        # yazılması Stripe tarafından zorunlu (yoksa "customer_update required" hatası).
        params["customer_update"] = {"address": "auto", "name": "auto"}
    session = stripe.checkout.Session.create(**params)
    return session.url


def create_portal_session(settings: Settings, *, customer_id: str, return_url: str) -> str:
    stripe = _stripe()
    stripe.api_key = settings.stripe_secret_key
    session = stripe.billing_portal.Session.create(customer=customer_id, return_url=return_url)
    return session.url


def construct_event(settings: Settings, payload: bytes, sig_header: str) -> dict:
    stripe = _stripe()
    return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
