"""Üretim orkestrasyonu — grounding + kurallar + prompt + model çağrısı.

Tek genel akış: etiketleri çöz → envanter kayıtlarını getir → global + türe özel
kuralları topla → prompt kur → model çağır → disclaimer'ı garanti et → yanıt kur.
Tüm IO bağımlılıkları (grounding repo, kural repo, model provider) enjekte edilir.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from .grounding import Grounding
from .models import GenerateRequest, GenerateResponse, Usage
from .prompt import DEFAULT_PROCESS_CAP, DISCLAIMER, build_prompt, ensure_disclaimer
from .provider import DEFAULT_MAX_TOKENS, ModelProvider
from .rules import GLOBAL_RULES, BusinessRuleRepository


def _user_input(request: GenerateRequest) -> dict:
    return {
        "type": request.type.value,
        "fields": request.fields,
        "veriler": request.veriler,
        "amaclar": request.amaclar,
    }


def generate_document(
    request: GenerateRequest,
    *,
    grounding: Grounding,
    rules_repo: BusinessRuleRepository,
    provider: ModelProvider,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    sector: str | None = None,
    kisi_grubu: str | None = None,
    process_cap: int = DEFAULT_PROCESS_CAP,
) -> GenerateResponse:
    doc_type = request.type.value

    # Etiket kaynağı: web kontratında çerez/risk kategorileri de 'veriler' altında gelir.
    tags = list(request.veriler)

    inventory = grounding.inventory_rules(tags)
    rules = GLOBAL_RULES + rules_repo.business_rules(doc_type)
    processes = grounding.process_rules(sector, kisi_grubu)
    prompt = build_prompt(
        doc_type, _user_input(request), inventory, rules, processes=processes, process_cap=process_cap
    )

    result = provider.generate(prompt, max_tokens=max_tokens)
    text = ensure_disclaimer(result.text)

    return GenerateResponse(
        text=text,
        grounding=[r.to_grounding() for r in inventory],
        model=result.model,
        disclaimer=DISCLAIMER,
        usage=Usage(input_tokens=result.input_tokens, output_tokens=result.output_tokens),
    )


def generate_document_stream(
    request: GenerateRequest,
    *,
    grounding: Grounding,
    rules_repo: BusinessRuleRepository,
    provider: Any,  # stream() metoduna sahip bir ModelProvider (duck-typed)
    max_tokens: int = DEFAULT_MAX_TOKENS,
    sector: str | None = None,
    kisi_grubu: str | None = None,
    process_cap: int = DEFAULT_PROCESS_CAP,
) -> Iterator[tuple[str, Any]]:
    """Olay akışı üretir: ('grounding', records) → ('delta', text)* → ('done', meta).

    Önce grounding kayıtları (anında şeffaflık paneli), sonra metin delta'ları,
    son olarak model/usage/disclaimer meta'sı yayınlanır. Disclaimer model çıktısında
    yoksa eklenen kuyruk son bir 'delta' olarak akıtılır (UI metniyle tutarlılık).
    """
    doc_type = request.type.value
    tags = list(request.veriler)

    inventory = grounding.inventory_rules(tags)
    yield ("grounding", [r.to_grounding() for r in inventory])

    rules = GLOBAL_RULES + rules_repo.business_rules(doc_type)
    processes = grounding.process_rules(sector, kisi_grubu)
    prompt = build_prompt(
        doc_type, _user_input(request), inventory, rules, processes=processes, process_cap=process_cap
    )

    chunks: list[str] = []
    for delta in provider.stream(prompt, max_tokens=max_tokens):
        chunks.append(delta)
        yield ("delta", delta)

    streamed = "".join(chunks)
    final_text = ensure_disclaimer(streamed)
    if final_text != streamed:
        yield ("delta", final_text[len(streamed):])

    last = getattr(provider, "last_result", None)
    yield (
        "done",
        {
            "model": getattr(provider, "model", "") or "",
            "disclaimer": DISCLAIMER,
            "usage": (
                {"inputTokens": last.input_tokens, "outputTokens": last.output_tokens}
                if last
                else None
            ),
        },
    )
