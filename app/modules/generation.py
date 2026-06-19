"""Generation modülü — POST /api/generate.

Grounding + iş kuralları Postgres'ten; model çağrısı BYOK (X-Anthropic-Key başlığı)
veya managed (sunucu anahtarı). Çekirdek mantık legal_core.generate_document'ta.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from legal_core import GenerateRequest, GenerateResponse, generate_document
from legal_core.grounding import Grounding
from legal_core.provider import AnthropicProvider

from ..config import get_settings
from ..db import get_session
from ..repositories import PostgresBusinessRuleRepository, PostgresCategoryRepository
from .auth import Tenant, get_current_tenant

router = APIRouter(prefix="/api", tags=["generation"])


@router.post("/generate", response_model=GenerateResponse, response_model_by_alias=True)
def generate(
    req: GenerateRequest,
    session: Session = Depends(get_session),
    tenant: Tenant = Depends(get_current_tenant),
    x_anthropic_key: str | None = Header(default=None, alias="X-Anthropic-Key"),
) -> GenerateResponse:
    settings = get_settings()

    # BYOK öncelikli; yoksa managed sunucu anahtarı.
    api_key = x_anthropic_key or settings.managed_anthropic_api_key
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="API anahtarı yok. BYOK için 'X-Anthropic-Key' başlığı gönderin "
            "veya sunucuda MANAGED_ANTHROPIC_API_KEY tanımlayın.",
        )

    grounding = Grounding(PostgresCategoryRepository(session))
    rules_repo = PostgresBusinessRuleRepository(session)
    provider = AnthropicProvider(api_key, model=settings.default_model)

    try:
        return generate_document(
            req,
            grounding=grounding,
            rules_repo=rules_repo,
            provider=provider,
            max_tokens=settings.max_tokens,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Üretim hatası: {e}")
