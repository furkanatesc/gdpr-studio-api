"""Üretim orkestrasyonu — grounding + kurallar + prompt + model çağrısı.

Tek genel akış: etiketleri çöz → envanter kayıtlarını getir → global + türe özel
kuralları topla → prompt kur → model çağır → disclaimer'ı garanti et → yanıt kur.
Tüm IO bağımlılıkları (grounding repo, kural repo, model provider) enjekte edilir.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import Any

from .aggregate_sections import Section
from .dpa_scope import DpaScope
from .grounding import Grounding
from .ihlal import build_ihlal_ilgili_kisi_prompt, build_ihlal_kurul_prompt
from .models import (
    ClientProfile,
    GenerateRequest,
    GenerateResponse,
    GroundingRecord,
    ProcessorInfo,
    ProcessRecord,
    Usage,
)
from .prompt import (
    DEFAULT_PROCESS_CAP,
    DISCLAIMER,
    build_aydinlatma_envanter_prompt,
    build_dpa_envanter_prompt,
    build_dpia_envanter_prompt,
    build_kayit_envanter_prompt,
    build_prompt,
    ensure_disclaimer,
)
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
    measures = grounding.measures()
    rules = GLOBAL_RULES + rules_repo.business_rules(doc_type)
    processes = grounding.process_rules(sector, kisi_grubu)
    prompt = build_prompt(
        doc_type, _user_input(request), inventory, rules,
        processes=processes, process_cap=process_cap, measures=measures,
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

    measures = grounding.measures()
    rules = GLOBAL_RULES + rules_repo.business_rules(doc_type)
    processes = grounding.process_rules(sector, kisi_grubu)
    prompt = build_prompt(
        doc_type, _user_input(request), inventory, rules,
        processes=processes, process_cap=process_cap, measures=measures,
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
            "stopReason": last.stop_reason if last else None,
        },
    )


async def generate_document_stream_async(
    request: GenerateRequest,
    *,
    grounding: Grounding,
    rules_repo: BusinessRuleRepository,
    provider: Any,  # astream() metoduna sahip bir AsyncModelProvider (duck-typed)
    max_tokens: int = DEFAULT_MAX_TOKENS,
    sector: str | None = None,
    kisi_grubu: str | None = None,
    process_cap: int = DEFAULT_PROCESS_CAP,
) -> AsyncIterator[tuple[str, Any]]:
    """generate_document_stream'in async ikizi: TEK fark `async for provider.astream`."""
    doc_type = request.type.value
    tags = list(request.veriler)

    inventory = grounding.inventory_rules(tags)
    yield ("grounding", [r.to_grounding() for r in inventory])

    measures = grounding.measures()
    rules = GLOBAL_RULES + rules_repo.business_rules(doc_type)
    processes = grounding.process_rules(sector, kisi_grubu)
    prompt = build_prompt(
        doc_type, _user_input(request), inventory, rules,
        processes=processes, process_cap=process_cap, measures=measures,
    )

    chunks: list[str] = []
    async for delta in provider.astream(prompt, max_tokens=max_tokens):
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
            "stopReason": last.stop_reason if last else None,
        },
    )


def _section_to_grounding(section: Section) -> GroundingRecord:
    return GroundingRecord(
        kategori=section.is_sureci,
        veri_turleri=section.veri_turleri,
        amaclar=section.amaclar,
        hukuki_sebepler=section.hukuki_sebepler,
        kisi_gruplari=section.kisi_gruplari,
        saklama_sureleri=section.saklama_sureleri,
    )


def generate_aydinlatma_envanter_stream(
    sections: list[Section],
    boilerplate: dict,
    profile: ClientProfile,
    *,
    provider: Any,  # stream() metoduna sahip bir ModelProvider (duck-typed)
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Iterator[tuple[str, Any]]:
    """Onaylı envanter bölümlerinden Aydınlatma Metni üretir — aydinlatma-envanter modu.

    generate_document_stream'in olay desenini birebir taklit eder: ('grounding', records) →
    ('delta', text)* → ('done', meta). Fark: prompt build_aydinlatma_envanter_prompt'tan
    gelir (m.10'un altı başlığı koşulsuz basan mod).
    """
    yield ("grounding", [_section_to_grounding(s) for s in sections])

    prompt = build_aydinlatma_envanter_prompt(sections, boilerplate, profile)

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
            "stopReason": last.stop_reason if last else None,
        },
    )


async def generate_aydinlatma_envanter_stream_async(
    sections: list[Section],
    boilerplate: dict,
    profile: ClientProfile,
    *,
    provider: Any,  # astream() metoduna sahip bir AsyncModelProvider (duck-typed)
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> AsyncIterator[tuple[str, Any]]:
    """generate_aydinlatma_envanter_stream'in async ikizi: TEK fark `async for provider.astream`."""
    yield ("grounding", [_section_to_grounding(s) for s in sections])

    prompt = build_aydinlatma_envanter_prompt(sections, boilerplate, profile)

    chunks: list[str] = []
    async for delta in provider.astream(prompt, max_tokens=max_tokens):
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
            "stopReason": last.stop_reason if last else None,
        },
    )


def _process_to_grounding(record: ProcessRecord) -> GroundingRecord:
    return GroundingRecord(
        kategori=record.is_sureci or record.departman,
        veri_turleri=record.veri_turleri,
        amaclar=record.amaclar,
        hukuki_sebepler=record.hukuki_sebepler,
        kisi_gruplari=[record.kisi_grubu] if record.kisi_grubu else [],
        saklama_sureleri=record.saklama_sureleri,
    )


def generate_kayit_envanter_stream(
    records: list[ProcessRecord],
    profile: ClientProfile,
    measures: list[str],
    rules: list[str],
    *,
    provider: Any,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    process_cap: int = DEFAULT_PROCESS_CAP,
) -> Iterator[tuple[str, Any]]:
    """Müvekkil envanterinden İşleme Kaydı üretir — aydinlatma envanter-modu deseni.

    Grounding olayı, format_kayit_processes'in prompt'a soktuğu aynı kırpılmış kümeyi
    yayınlar (process_cap==0 sınırsız demektir — prompt ile tutarlı kalır).
    """
    total = len(records)
    grounded = records[:process_cap] if process_cap and total > process_cap else records
    yield ("grounding", [_process_to_grounding(r) for r in grounded])

    prompt = build_kayit_envanter_prompt(records, profile, measures, rules, process_cap=process_cap)

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
            "stopReason": last.stop_reason if last else None,
        },
    )


async def generate_kayit_envanter_stream_async(
    records: list[ProcessRecord],
    profile: ClientProfile,
    measures: list[str],
    rules: list[str],
    *,
    provider: Any,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    process_cap: int = DEFAULT_PROCESS_CAP,
) -> AsyncIterator[tuple[str, Any]]:
    """generate_kayit_envanter_stream'in async ikizi: TEK fark `async for provider.astream`."""
    total = len(records)
    grounded = records[:process_cap] if process_cap and total > process_cap else records
    yield ("grounding", [_process_to_grounding(r) for r in grounded])

    prompt = build_kayit_envanter_prompt(records, profile, measures, rules, process_cap=process_cap)

    chunks: list[str] = []
    async for delta in provider.astream(prompt, max_tokens=max_tokens):
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
            "stopReason": last.stop_reason if last else None,
        },
    )


def generate_dpia_envanter_stream(
    records: list[ProcessRecord],
    profile: ClientProfile,
    measures: list[str],
    rules: list[str],
    tetiklenenler: list[str],
    *,
    provider: Any,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    process_cap: int = DEFAULT_PROCESS_CAP,
) -> Iterator[tuple[str, Any]]:
    """Muvekkil envanterinden DPIA taslagi uretir — kayit envanter-modu deseni."""
    total = len(records)
    grounded = records[:process_cap] if process_cap and total > process_cap else records
    yield ("grounding", [_process_to_grounding(r) for r in grounded])

    prompt = build_dpia_envanter_prompt(records, profile, measures, rules, tetiklenenler,
                                        process_cap=process_cap)

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
            "stopReason": last.stop_reason if last else None,
        },
    )


async def generate_dpia_envanter_stream_async(
    records: list[ProcessRecord],
    profile: ClientProfile,
    measures: list[str],
    rules: list[str],
    tetiklenenler: list[str],
    *,
    provider: Any,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    process_cap: int = DEFAULT_PROCESS_CAP,
) -> AsyncIterator[tuple[str, Any]]:
    """generate_dpia_envanter_stream'in async ikizi: TEK fark `async for provider.astream`."""
    total = len(records)
    grounded = records[:process_cap] if process_cap and total > process_cap else records
    yield ("grounding", [_process_to_grounding(r) for r in grounded])

    prompt = build_dpia_envanter_prompt(records, profile, measures, rules, tetiklenenler,
                                        process_cap=process_cap)

    chunks: list[str] = []
    async for delta in provider.astream(prompt, max_tokens=max_tokens):
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
            "stopReason": last.stop_reason if last else None,
        },
    )


def generate_dpa_envanter_stream(
    scope: DpaScope,
    profile: ClientProfile,
    processor: ProcessorInfo,
    measures: list[str],
    rules: list[str],
    *,
    provider: Any,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    process_cap: int = DEFAULT_PROCESS_CAP,
) -> Iterator[tuple[str, Any]]:
    """İşleyene aktarılan süreç kapsamından DPA taslağı üretir — dpia envanter-modu deseni."""
    total = len(scope.eslesen_surecler)
    grounded = scope.eslesen_surecler[:process_cap] if process_cap and total > process_cap else scope.eslesen_surecler
    yield ("grounding", [_process_to_grounding(r) for r in grounded])

    prompt = build_dpa_envanter_prompt(scope, profile, processor, measures, rules, process_cap=process_cap)

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
                if last else None
            ),
            "stopReason": last.stop_reason if last else None,
        },
    )


async def generate_dpa_envanter_stream_async(
    scope: DpaScope,
    profile: ClientProfile,
    processor: ProcessorInfo,
    measures: list[str],
    rules: list[str],
    *,
    provider: Any,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    process_cap: int = DEFAULT_PROCESS_CAP,
) -> AsyncIterator[tuple[str, Any]]:
    """generate_dpa_envanter_stream'in async ikizi: TEK fark `async for provider.astream`."""
    total = len(scope.eslesen_surecler)
    grounded = scope.eslesen_surecler[:process_cap] if process_cap and total > process_cap else scope.eslesen_surecler
    yield ("grounding", [_process_to_grounding(r) for r in grounded])

    prompt = build_dpa_envanter_prompt(scope, profile, processor, measures, rules, process_cap=process_cap)

    chunks: list[str] = []
    async for delta in provider.astream(prompt, max_tokens=max_tokens):
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
                if last else None
            ),
            "stopReason": last.stop_reason if last else None,
        },
    )


def generate_ihlal_stream(
    olay,
    profile,
    kategoriler,
    veri_turleri,
    measures,
    rules,
    bildirim_turu,
    *,
    provider: Any,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Iterator[tuple[str, Any]]:
    """İhlal bildirimi üretir (kurul | ilgili_kisi) — dpia stream deseni, grounding'siz."""
    if bildirim_turu == "kurul":
        prompt = build_ihlal_kurul_prompt(olay, profile, kategoriler, veri_turleri, measures, rules)
    else:
        prompt = build_ihlal_ilgili_kisi_prompt(olay, profile, kategoriler)

    chunks: list[str] = []
    for delta in provider.stream(prompt, max_tokens=max_tokens):
        chunks.append(delta)
        yield ("delta", delta)
    streamed = "".join(chunks)
    final_text = ensure_disclaimer(streamed)
    if final_text != streamed:
        yield ("delta", final_text[len(streamed):])
    last = getattr(provider, "last_result", None)
    yield ("done", {
        "model": getattr(provider, "model", "") or "",
        "disclaimer": DISCLAIMER,
        "usage": ({"inputTokens": last.input_tokens, "outputTokens": last.output_tokens} if last else None),
        "stopReason": last.stop_reason if last else None,
    })


async def generate_ihlal_stream_async(
    olay,
    profile,
    kategoriler,
    veri_turleri,
    measures,
    rules,
    bildirim_turu,
    *,
    provider: Any,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> AsyncIterator[tuple[str, Any]]:
    """generate_ihlal_stream'in async ikizi: TEK fark `async for provider.astream`."""
    if bildirim_turu == "kurul":
        prompt = build_ihlal_kurul_prompt(olay, profile, kategoriler, veri_turleri, measures, rules)
    else:
        prompt = build_ihlal_ilgili_kisi_prompt(olay, profile, kategoriler)

    chunks: list[str] = []
    async for delta in provider.astream(prompt, max_tokens=max_tokens):
        chunks.append(delta)
        yield ("delta", delta)
    streamed = "".join(chunks)
    final_text = ensure_disclaimer(streamed)
    if final_text != streamed:
        yield ("delta", final_text[len(streamed):])
    last = getattr(provider, "last_result", None)
    yield ("done", {
        "model": getattr(provider, "model", "") or "",
        "disclaimer": DISCLAIMER,
        "usage": ({"inputTokens": last.input_tokens, "outputTokens": last.output_tokens} if last else None),
        "stopReason": last.stop_reason if last else None,
    })
