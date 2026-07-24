"""Saf fiyat + bütçe tablosu (managed maliyet guardrail). Yan etkisiz (log hariç)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Model → (input $/1M token, output $/1M token). Anthropic referansı (2026-06).
PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),  # managed default_model
    "claude-opus-4-8": (5.0, 25.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

# Plan → aylık maliyet tavanı (USD micros). 1 USD = 1_000_000 micros.
COST_BUDGET_MICROS: dict[str, int] = {
    # 5-dok tavanı billing_enabled'a bağlı (Stripe kurulu değilken uygulanmaz), bu yüzden
    # ücretsiz planda BAĞLAYICI sınır bu backstop'tur. ~$0.13/belge → ~75 belge/ay.
    # Stripe açılıp doküman tavanı devreye girince $2'ye çekilebilir.
    "baslangic": 10_000_000,   # $10 backstop
    "standart": 40_000_000,    # $40
    "premium": 150_000_000,    # $150
}


def cost_micros(model: str, input_tokens: int, output_tokens: int) -> int:
    """Üretim maliyeti (USD micros). $/Mtok × token doğrudan micros verir."""
    price = PRICING.get(model)
    if price is None:
        logger.warning("Bilinmeyen model fiyatı: %s — maliyet 0 sayıldı", model)
        return 0
    in_p, out_p = price
    return round(input_tokens * in_p + output_tokens * out_p)


def cost_budget_for(plan: str) -> int | None:
    """Plan aylık maliyet tavanı (USD micros). Bilinmeyen plan → None (tavan yok)."""
    return COST_BUDGET_MICROS.get(plan)
