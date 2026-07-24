# app/modules/kayit.py
"""Isleme kaydi (VERBIS) uretimi — muvekkil envanterinden generate/docx uclari.

Aydinlatma/cerez generate skeleton'ini izler; fark: girdi muvekkilin client_processes
envanteri (generate_kayit_envanter_stream) ve doc_type='kayit' saklama.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from legal_core.generate import generate_kayit_envanter_stream
from legal_core.models import DocType
from legal_core.prompt import ensure_disclaimer
from legal_core.provider import AnthropicProvider
from legal_core.rules import GLOBAL_RULES
from legal_core.scoring import kayit_completeness_score

from .. import idempotency
from ..auth.identity import Identity, get_current_identity
from ..auth.tenant_session import tenant_session
from ..billing.quota import (
    enforce_generation_quota,
    reserve_generation_usage,
    settle_generation_usage,
)
from ..config import get_settings
from ..docx_export import render_docx
from ..observability import capture_exception
from ..redis_client import generate_rate_limit
from ..repositories import (
    ClientRepository,
    GeneratedDocumentRepository,
    PostgresBusinessRuleRepository,
    PostgresMeasureRepository,
    PostgresProcessRepository,
)
from .document_store import client_profile, store_client_document
from .generation import _claim_idempotency, _resolve_api_key, _sse

router = APIRouter(prefix="/api/clients", tags=["kayit"])
_log = logging.getLogger("app.kayit")


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class DocxIn(_Camel):
    text: str
    title: str | None = None


@router.post("/{client_id}/kayit/generate", dependencies=[Depends(generate_rate_limit)])
def generate(
    client_id: uuid.UUID,
    session: Session = Depends(tenant_session),
    identity: Identity = Depends(enforce_generation_quota),
    x_anthropic_key: str | None = Header(default=None, alias="X-Anthropic-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> StreamingResponse:
    """Muvekkil envanterinden Isleme Kaydi (VERBIS) akisi (SSE)."""
    settings = get_settings()

    client = ClientRepository(session).get(identity.org_id, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")

    records = PostgresProcessRepository(session).client_processes(client_id)
    if not records:
        raise HTTPException(
            status_code=422,
            detail="Envanterde işleme kaydı için süreç bulunamadı — önce envanter girin.",
        )

    api_key = _resolve_api_key(x_anthropic_key)
    _claim_idempotency(identity, idempotency_key)

    prof = client_profile(client)
    measures = PostgresMeasureRepository(session).all_measures()
    rules = GLOBAL_RULES + PostgresBusinessRuleRepository(session).business_rules("kayit")
    cap = settings.process_cap
    scored_records = records[:cap] if cap else records
    provider = AnthropicProvider(
        api_key,
        model=settings.default_model,
        timeout_s=settings.anthropic_timeout_s,
        max_retries=settings.anthropic_max_retries,
    )
    byok = x_anthropic_key is not None

    def event_stream():
        reserved = 0
        started = False
        full_text = ""
        try:
            for kind, payload in generate_kayit_envanter_stream(
                records, prof, measures, rules, provider=provider, max_tokens=settings.max_tokens,
                process_cap=cap,
            ):
                if kind == "grounding":
                    yield _sse("grounding", [g.model_dump(by_alias=True) for g in payload])
                elif kind == "delta":
                    if not started:
                        started = True
                        GeneratedDocumentRepository(session).record(identity.org_id, DocType.kayit)
                        reserved = reserve_generation_usage(
                            session, settings, identity.org_id,
                            model=settings.default_model, byok=byok,
                        )
                    full_text += payload
                    yield _sse("delta", {"text": payload})
                elif kind == "done":
                    yield _sse("done", payload)
                    usage = payload.get("usage")
                    settle_generation_usage(
                        session, settings, identity.org_id,
                        model=payload.get("model") or settings.default_model,
                        input_tokens=usage["inputTokens"] if usage else 0,
                        output_tokens=usage["outputTokens"] if usage else 0,
                        byok=byok, reserved_micros=reserved,
                    )
                    try:
                        store_client_document(
                            session, identity.org_id, client_id, "kayit", "İşleme Kaydı",
                            ensure_disclaimer(full_text), kayit_completeness_score(scored_records),
                        )
                    except Exception as store_err:  # best-effort; PII'siz log
                        _log.error("kayit saklama basarisiz (org=%s): %s", identity.org_id, type(store_err).__name__)
        except Exception as e:
            if not started:
                idempotency.release(identity.org_id, idempotency_key)
            _log.exception("kayit akis hatasi (org=%s)", identity.org_id)
            capture_exception(e)
            yield _sse("error", {"detail": f"Üretim hatası: {e}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/{client_id}/kayit/docx")
def docx(
    client_id: uuid.UUID,
    body: DocxIn,
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(tenant_session),
) -> Response:
    if ClientRepository(session).get(identity.org_id, client_id) is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")
    data = render_docx(body.text, body.title or "İşleme Kaydı")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="isleme-kaydi.docx"'},
    )
