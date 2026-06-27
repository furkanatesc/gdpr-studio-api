# backend/tests/test_stripe_client.py
import types

import pytest

from app.billing import stripe_client
from app.config import Settings


@pytest.fixture()
def settings():
    return Settings(_env_file=None, stripe_secret_key="sk_test_x", stripe_webhook_secret="whsec_x")


def test_create_checkout_session_builds_params(monkeypatch, settings):
    captured = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(url="https://checkout.stripe.test/abc")

    fake_stripe = types.SimpleNamespace(
        checkout=types.SimpleNamespace(Session=types.SimpleNamespace(create=fake_create)),
        api_key=None,
    )
    monkeypatch.setattr(stripe_client, "_stripe", lambda: fake_stripe)

    url = stripe_client.create_checkout_session(
        settings,
        price_id="price_sy",
        org_id="org-1",
        customer_id=None,
        success_url="https://app/ok",
        cancel_url="https://app/no",
    )
    assert url == "https://checkout.stripe.test/abc"
    assert captured["mode"] == "subscription"
    assert captured["client_reference_id"] == "org-1"
    assert captured["line_items"] == [{"price": "price_sy", "quantity": 1}]
    assert captured["subscription_data"]["metadata"]["org_id"] == "org-1"
    assert "customer" not in captured  # customer_id None → Stripe yeni müşteri yaratır


def test_create_checkout_attaches_existing_customer(monkeypatch, settings):
    captured = {}
    fake_stripe = types.SimpleNamespace(
        checkout=types.SimpleNamespace(
            Session=types.SimpleNamespace(
                create=lambda **kw: captured.update(kw) or types.SimpleNamespace(url="u")
            )
        ),
        api_key=None,
    )
    monkeypatch.setattr(stripe_client, "_stripe", lambda: fake_stripe)
    stripe_client.create_checkout_session(
        settings, price_id="p", org_id="o", customer_id="cus_7",
        success_url="s", cancel_url="c",
    )
    assert captured["customer"] == "cus_7"


def test_construct_event_delegates_to_stripe(monkeypatch, settings):
    fake_stripe = types.SimpleNamespace(
        Webhook=types.SimpleNamespace(
            construct_event=lambda payload, sig, secret: {"id": "evt_1", "type": "x", "_secret": secret}
        ),
        api_key=None,
    )
    monkeypatch.setattr(stripe_client, "_stripe", lambda: fake_stripe)
    ev = stripe_client.construct_event(settings, b"{}", "sig")
    assert ev["id"] == "evt_1" and ev["_secret"] == "whsec_x"
