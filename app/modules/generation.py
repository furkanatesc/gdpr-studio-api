"""Generation modülü — POST /api/generate.

Grounding + iş kuralları Postgres'ten; model çağrısı BYOK (X-Anthropic-Key başlığı)
veya managed (sunucu anahtarı). Çekirdek mantık legal_core.generate_document'ta.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from legal_core import GenerateRequest, GenerateResponse, generate_document
from legal_core.generate import generate_document_stream
from legal_core.grounding import Grounding
from legal_core.provider import AnthropicProvider

from ..auth.identity import Identity
from ..auth.tenant_session import tenant_session
from ..billing.quota import enforce_generation_quota, record_generation_usage
from ..config import get_settings
from ..redis_client import generate_rate_limit
from ..repositories import (
    GeneratedDocumentRepository,
    PostgresBusinessRuleRepository,
    PostgresCategoryRepository,
)
from ..semantic import PostgresSemanticMatcher, get_embedder

router = APIRouter(prefix="/api", tags=["generation"])


def _build_grounding(session: Session, settings) -> Grounding:
    """Env-gated grounding: semantic_fallback_enabled ise pgvector matcher enjekte edilir."""
    repo = PostgresCategoryRepository(session)
    if settings.semantic_fallback_enabled:
        matcher = PostgresSemanticMatcher(
            session, get_embedder(settings), settings.semantic_threshold
        )
        return Grounding(repo, matcher=matcher)
    return Grounding(repo)


def _resolve_api_key(x_anthropic_key: str | None) -> str:
    """BYOK öncelikli; yoksa managed sunucu anahtarı. Yoksa 400."""
    api_key = x_anthropic_key or get_settings().managed_anthropic_api_key
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="API anahtarı yok. BYOK için 'X-Anthropic-Key' başlığı gönderin "
            "veya sunucuda MANAGED_ANTHROPIC_API_KEY tanımlayın.",
        )
    return api_key


def _sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post(
    "/generate",
    response_model=GenerateResponse,
    response_model_by_alias=True,
    dependencies=[Depends(generate_rate_limit)],
)
def generate(
    req: GenerateRequest,
    # tenant_session: RLS org bağlamını set eder; record_generation_usage bu oturumda yazar.
    session: Session = Depends(tenant_session),
    identity: Identity = Depends(enforce_generation_quota),
    x_anthropic_key: str | None = Header(default=None, alias="X-Anthropic-Key"),
) -> GenerateResponse:
    settings = get_settings()
    api_key = _resolve_api_key(x_anthropic_key)

    grounding = _build_grounding(session, settings)
    rules_repo = PostgresBusinessRuleRepository(session)
    provider = AnthropicProvider(api_key, model=settings.default_model)

    try:
        result = generate_document(
            req,
            grounding=grounding,
            rules_repo=rules_repo,
            provider=provider,
            max_tokens=settings.max_tokens,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Üretim hatası: {e}") from e
    # Uyum sinyali: başarılı üretimi generated_documents'a yaz. record_generation_usage
    # commit ettiği için kayıt ONDAN ÖNCE flush'lanır → aynı işlemde persist olur (spec §4).
    GeneratedDocumentRepository(session).record(identity.org_id, req.type)
    record_generation_usage(
        session,
        settings,
        identity.org_id,
        model=result.model,
        input_tokens=result.usage.input_tokens,
        output_tokens=result.usage.output_tokens,
        byok=x_anthropic_key is not None,
    )  # yalnız başarıda
    return result


@router.post("/generate/stream", dependencies=[Depends(generate_rate_limit)])
def generate_stream(
    req: GenerateRequest,
    # tenant_session: RLS org bağlamını set eder; record_generation_usage bu oturumda yazar.
    session: Session = Depends(tenant_session),
    identity: Identity = Depends(enforce_generation_quota),
    x_anthropic_key: str | None = Header(default=None, alias="X-Anthropic-Key"),
) -> StreamingResponse:
    """Streaming (SSE): grounding → metin delta'ları → done. Algılanan gecikmeyi düşürür."""
    settings = get_settings()
    api_key = _resolve_api_key(x_anthropic_key)

    grounding = _build_grounding(session, settings)
    rules_repo = PostgresBusinessRuleRepository(session)
    provider = AnthropicProvider(api_key, model=settings.default_model)

    def event_stream():
        try:
            for kind, payload in generate_document_stream(
                req,
                grounding=grounding,
                rules_repo=rules_repo,
                provider=provider,
                max_tokens=settings.max_tokens,
            ):
                if kind == "grounding":
                    yield _sse("grounding", [g.model_dump(by_alias=True) for g in payload])
                elif kind == "delta":
                    yield _sse("delta", {"text": payload})
                elif kind == "done":
                    yield _sse("done", payload)
                    usage = payload.get("usage")
                    # Uyum sinyali (aynı işlemde, record_generation_usage commit'inden önce).
                    GeneratedDocumentRepository(session).record(identity.org_id, req.type)
                    record_generation_usage(
                        session,
                        settings,
                        identity.org_id,
                        model=payload.get("model") or settings.default_model,
                        input_tokens=usage["inputTokens"] if usage else 0,
                        output_tokens=usage["outputTokens"] if usage else 0,
                        byok=x_anthropic_key is not None,
                    )  # akış başarıyla bitti
        except Exception as e:  # akış ortasında hata → error olayı
            yield _sse("error", {"detail": f"Üretim hatası: {e}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
