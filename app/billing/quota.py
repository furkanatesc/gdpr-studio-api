"""Kota + maliyet enforcement + kullanım/maliyet sayımı (generate uçları için)."""

from __future__ import annotations

import uuid

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..auth.identity import Identity, get_current_identity
from ..auth.tenant_session import set_org_context, tenant_session
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

    Maliyet bütçesi Stripe'tan BAĞIMSIZ uygulanır: managed anahtarın harcaması
    ödeme sağlayıcısının kurulu olmasına bağlı olamaz. Doküman tavanı ise gelir
    kapısıdır — yükseltme yolu (checkout) yokken kullanıcıyı engellemek anlamsız,
    o yüzden billing_enabled'a bağlı kalır.
    """
    settings = get_settings()
    ent = resolve_entitlement(session, identity.org_id)
    # (1) Ücretsiz doküman tavanı — yalnız checkout mümkünken
    if settings.billing_enabled and ent.quota is not None and ent.used >= ent.quota:
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
    set_org_context(session, org_id)
    repo = UsageRepository(session)
    repo.increment(org_id, current_period())  # doküman sayımı (BYOK dahil — mevcut davranış)
    if not byok:
        cm = cost_micros(model, input_tokens, output_tokens)
        repo.add_cost(org_id, current_period(), input_tokens, output_tokens, cm)
    session.commit()


def reserve_generation_usage(
    session: Session,
    settings: Settings,
    org_id: uuid.UUID,
    *,
    model: str,
    byok: bool,
    max_tokens: int | None = None,
) -> int:
    """Akış üretiminde model çağrısı başlar başlamaz sayımı REZERVE eder; rezerve maliyeti döner.

    Neden rezervasyon: istemci 'done' olayından önce koparsa üretecin `finally`'si ancak çöp
    toplamada çalışır ve o an istek oturumu kapanmış olabilir → oradan yazmak kaybolabilir.
    Sayım bu yüzden akış CANLIYKEN (ilk delta) yazılır; koparan istemci rezervasyonu üstlenir.

    Maliyet, tokenlar daha bilinmediği için en kötü durumdan (tam çıktı tavanı) rezerve edilir;
    'done' gelince `settle_generation_usage` gerçek maliyetle mahsuplaşır. Böylece erken kopma
    maliyet bütçesini atlatmaz — aksine pahalı sayılır (kötüye kullanım teşviki yok). Çağıran,
    üretimde GERÇEKTEN kullanılan tavanı `max_tokens` ile geçmeli (ör. 'kayit' 32000 kullanıyorsa
    burada da 32000 geçilmeli — aksi halde rezervasyon eksik kalır ve guardrail atlatılabilir).
    Verilmezse mevcut davranış korunur: `settings.max_tokens` (8000).
    Rezerve maliyet bir guardrail sayacıdır; müşteriye fatura edilmez (Stripe aboneliği faturalar).
    """
    cap = max_tokens if max_tokens is not None else settings.max_tokens
    set_org_context(session, org_id)
    repo = UsageRepository(session)
    repo.increment(org_id, current_period())  # doküman sayımı (BYOK dahil — mevcut davranış)
    reserved = 0
    if not byok:
        reserved = cost_micros(model, 0, cap)
        repo.add_cost(org_id, current_period(), 0, 0, reserved)  # token'lar 'done'da yazılır
    session.commit()
    return reserved


def settle_generation_usage(
    session: Session,
    settings: Settings,
    org_id: uuid.UUID,
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    byok: bool,
    reserved_micros: int,
) -> None:
    """Akış 'done': gerçek token'ları yaz ve rezervasyon farkını düzelt (fark negatif olabilir)."""
    if byok:
        return
    # Rezervasyon commit'i app.current_org_id'yi sifirladi — RLS yazimi icin yeniden kur.
    set_org_context(session, org_id)
    actual = cost_micros(model, input_tokens, output_tokens)
    UsageRepository(session).add_cost(
        org_id,
        current_period(),
        input_tokens,
        output_tokens,
        actual - reserved_micros,
    )
    session.commit()
