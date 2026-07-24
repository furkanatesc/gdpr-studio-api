# app/modules/cerez.py
"""Cerez politikasi uretimi — muvekkil baglaminda generate/docx uclari.

Aydinlatma generate skeleton'ini (kota/idempotency/rate-limit/SSE) izler; fark: jenerik
generate_document_stream'i cerez girdisi + muvekkil kimligiyle cagirir ve client_documents'a
doc_type='cerez' saklar (ortak store_client_document, RLS-guvenli).
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from legal_core.generate import generate_document_stream
from legal_core.models import DocType, GenerateRequest
from legal_core.prompt import ensure_disclaimer
from legal_core.provider import AnthropicProvider
from legal_core.scoring import cerez_completeness_score

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
)
from .document_store import client_profile, store_client_document
from .generation import _build_grounding, _claim_idempotency, _resolve_api_key, _sse

router = APIRouter(prefix="/api/clients", tags=["cerez"])
_log = logging.getLogger("app.cerez")


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class CerezGenerateIn(_Camel):
    site: str = Field(min_length=1)
    tools: str = ""
    cmp: str = "yok"
    kategoriler: list[str] = []


class DocxIn(_Camel):
    text: str
    title: str | None = None


@router.post("/{client_id}/cerez/generate", dependencies=[Depends(generate_rate_limit)])
def generate(
    client_id: uuid.UUID,
    body: CerezGenerateIn,
    session: Session = Depends(tenant_session),
    identity: Identity = Depends(enforce_generation_quota),
    x_anthropic_key: str | None = Header(default=None, alias="X-Anthropic-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> StreamingResponse:
    """Muvekkil kimligi + form girdisinden Cerez Politikasi akisi (SSE)."""
    settings = get_settings()

    client = ClientRepository(session).get(identity.org_id, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")

    api_key = _resolve_api_key(x_anthropic_key)
    _claim_idempotency(identity, idempotency_key)

    prof = client_profile(client)
    fields = {
        "site": body.site,
        "veri_sorumlusu": prof.unvan or prof.ad or "",
        "adres": prof.adres or "",
        "kep": prof.kep or "",
        "eposta": prof.eposta or "",
        "arac_ucuncu_taraf": body.tools,
        "riza_yonetimi_cmp": body.cmp,
    }
    req = GenerateRequest(type=DocType.cerez, fields=fields, veriler=body.kategoriler)

    grounding = _build_grounding(session, settings)
    rules_repo = PostgresBusinessRuleRepository(session)
    provider = AnthropicProvider(
        api_key,
        model=settings.default_model,
        timeout_s=settings.anthropic_timeout_s,
        max_retries=settings.anthropic_max_retries,
    )
    byok = x_anthropic_key is not None

    def event_stream():
        # Sayim deseni generation.generate_stream ile birebir.
        reserved = 0
        started = False
        full_text = ""
        try:
            for kind, payload in generate_document_stream(
                req,
                grounding=grounding,
                rules_repo=rules_repo,
                provider=provider,
                max_tokens=settings.max_tokens,
                sector=client.sector,
                kisi_grubu=None,
                process_cap=settings.process_cap,
            ):
                if kind == "grounding":
                    yield _sse("grounding", [g.model_dump(by_alias=True) for g in payload])
                elif kind == "delta":
                    if not started:
                        started = True
                        GeneratedDocumentRepository(session).record(identity.org_id, DocType.cerez)
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
                    if payload.get("stopReason") == "max_tokens":
                        # Kesik belge tam puanla resmi kayit olarak SAKLANMAZ.
                        _log.warning(
                            "cerez uretimi kesildi (max_tokens): org=%s doc_type=cerez",
                            identity.org_id,
                        )
                        yield _sse("warning", {
                            "code": "truncated_max_tokens",
                            "message": (
                                "Belge, model çıktı uzunluğu sınırına takıldığı için eksik "
                                "kaldı ve KAYDEDİLMEDİ. Çerez kategori sayısını daraltıp "
                                "yeniden deneyin."
                            ),
                        })
                    else:
                        try:
                            store_client_document(
                                session, identity.org_id, client_id, "cerez",
                                (body.site or "Genel")[:255], ensure_disclaimer(full_text),
                                cerez_completeness_score(
                                    bool(prof.ad or prof.unvan), body.kategoriler, body.tools, body.cmp
                                ),
                            )
                        except Exception as store_err:  # best-effort; PII'siz log
                            _log.error(
                                "cerez saklama basarisiz (org=%s): %s",
                                identity.org_id, type(store_err).__name__,
                            )
        except Exception as e:
            if not started:
                idempotency.release(identity.org_id, idempotency_key)
            _log.exception("cerez akis hatasi (org=%s)", identity.org_id)
            capture_exception(e)
            yield _sse("error", {"detail": f"Üretim hatası: {e}"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/{client_id}/cerez/docx")
def docx(
    client_id: uuid.UUID,
    body: DocxIn,
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(tenant_session),
) -> Response:
    if ClientRepository(session).get(identity.org_id, client_id) is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")
    data = render_docx(body.text, body.title or "Çerez Politikası")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="cerez-politikasi.docx"'},
    )
