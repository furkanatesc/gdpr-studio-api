# app/modules/aydinlatma.py
"""Aydinlatma metni uretimi — musvekkil baglaminda prepare/generate/docx uclari.

generate ucu app.modules.generation.generate_stream'in kota/idempotency/rate-limit
desenini birebir kullanir; fark: onayli envanter bolumlerinden (Section) sabit
DocType.aydinlatma uretir (legal_core.generate.generate_aydinlatma_envanter_stream).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from legal_core.aggregate_sections import Section, aggregate_sections
from legal_core.boilerplate import load_boilerplate
from legal_core.canonical import load_canonicalizer
from legal_core.generate import generate_aydinlatma_envanter_stream
from legal_core.models import DocType
from legal_core.prompt import ensure_disclaimer
from legal_core.provider import AnthropicProvider
from legal_core.scoring import completeness_score

from .. import idempotency
from ..auth.identity import Identity, get_current_identity
from ..auth.tenant_session import tenant_session
from ..aydinlatma_enrich import EnrichedSection, enrich_sections
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
    ClientDocumentRepository,
    ClientRepository,
    GeneratedDocumentRepository,
    PostgresProcessRepository,
)
from .document_store import client_profile, store_client_document
from .generation import _claim_idempotency, _resolve_api_key, _sse

router = APIRouter(prefix="/api/clients", tags=["aydinlatma"])
_log = logging.getLogger("app.aydinlatma")
_CANON = load_canonicalizer()


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class PrepareIn(_Camel):
    target_groups: list[str] = Field(min_length=1)


class SectionIn(_Camel):
    is_sureci: str
    kisi_gruplari: list[str] = []
    kategoriler: list[str] = []
    veri_turleri: list[str] = []
    amaclar: list[str] = []
    hukuki_sebepler: list[str] = []
    saklama_sureleri: list[str] = []
    aktarim: list[str] = []
    toplama: list[str] = []


class GenerateIn(_Camel):
    sections: list[SectionIn] = Field(min_length=1)


class DocxIn(_Camel):
    text: str
    title: str | None = None


class EnrichedSectionOut(_Camel):
    is_sureci: str
    kisi_gruplari: list[str] = []
    kategoriler: list[str] = []
    veri_turleri: list[str] = []
    amaclar: list[str] = []
    hukuki_sebepler: list[str] = []
    saklama_sureleri: list[str] = []
    aktarim: list[str] = []
    toplama: list[str] = []
    oneriler: dict[str, list[str]] = {}


class PrepareOut(_Camel):
    sections: list[EnrichedSectionOut]


class ClientDocumentMetaOut(_Camel):
    id: uuid.UUID
    doc_type: str
    title: str
    score_completeness: float | None = None
    score_compliance: float | None = None
    created_at: datetime
    updated_at: datetime


class ClientDocumentsOut(_Camel):
    documents: list[ClientDocumentMetaOut]


class ClientDocumentOut(ClientDocumentMetaOut):
    content: str


def _enriched_to_out(es: EnrichedSection) -> EnrichedSectionOut:
    return EnrichedSectionOut(
        is_sureci=es.is_sureci,
        kisi_gruplari=es.kisi_gruplari,
        kategoriler=es.kategoriler,
        veri_turleri=es.veri_turleri,
        amaclar=es.amaclar,
        hukuki_sebepler=es.hukuki_sebepler,
        saklama_sureleri=es.saklama_sureleri,
        aktarim=es.aktarim,
        toplama=es.toplama,
        oneriler=es.oneriler,
    )


def _in_to_section(s: SectionIn) -> Section:
    return Section(
        is_sureci=s.is_sureci,
        kisi_gruplari=s.kisi_gruplari,
        kategoriler=s.kategoriler,
        veri_turleri=s.veri_turleri,
        amaclar=s.amaclar,
        hukuki_sebepler=s.hukuki_sebepler,
        saklama_sureleri=s.saklama_sureleri,
        aktarim=s.aktarim,
        toplama=s.toplama,
    )


def _derive_title(sections: list[Section]) -> str:
    seen: list[str] = []
    for s in sections:
        for kg in s.kisi_gruplari:
            if kg and kg not in seen:
                seen.append(kg)
    return (", ".join(seen))[:255] or "Genel"


def _store_generated_document(session, org_id, client_id, sections, content) -> None:
    """Best-effort aydinlatma saklama — ortak store_client_document uzerinden (RLS-guvenli)."""
    store_client_document(
        session, org_id, client_id, "aydinlatma", _derive_title(sections), content,
        completeness_score(sections),
    )


@router.post("/{client_id}/aydinlatma/prepare", response_model=PrepareOut, response_model_by_alias=True)
def prepare(
    client_id: uuid.UUID,
    body: PrepareIn,
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(tenant_session),
) -> PrepareOut:
    client = ClientRepository(session).get(identity.org_id, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")

    records = PostgresProcessRepository(session).client_processes(client_id)
    sections = aggregate_sections(records, body.target_groups, canonicalizer=_CANON)
    if not sections:
        raise HTTPException(
            status_code=422,
            detail="Seçilen hedef gruplar için envanterde iş süreci bulunamadı.",
        )

    enriched = enrich_sections(
        sections, client.sector or "sirket", PostgresProcessRepository(session), canonicalizer=_CANON
    )
    return PrepareOut(sections=[_enriched_to_out(e) for e in enriched])


@router.post("/{client_id}/aydinlatma/generate", dependencies=[Depends(generate_rate_limit)])
def generate(
    client_id: uuid.UUID,
    body: GenerateIn,
    # tenant_session: RLS org bağlamını set eder; record_generation_usage bu oturumda yazar.
    session: Session = Depends(tenant_session),
    identity: Identity = Depends(enforce_generation_quota),
    x_anthropic_key: str | None = Header(default=None, alias="X-Anthropic-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> StreamingResponse:
    """Onaylı envanter bölümlerinden Aydınlatma Metni akışı (SSE)."""
    settings = get_settings()

    # Sahiplik önce: 404 idempotency claim'inden ÖNCE — aksi halde geçersiz client_id +
    # bir Idempotency-Key ile gelen istek kilidi alır ama hiç bırakmaz (404 generator
    # dışında fırlar), sonraki geçerli deneme sahte 409 alır.
    client = ClientRepository(session).get(identity.org_id, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")

    api_key = _resolve_api_key(x_anthropic_key)
    _claim_idempotency(identity, idempotency_key)

    profile = client_profile(client)
    boilerplate = load_boilerplate()
    sections = [_in_to_section(s) for s in body.sections]
    provider = AnthropicProvider(
        api_key,
        model=settings.default_model,
        timeout_s=settings.anthropic_timeout_s,
        max_retries=settings.anthropic_max_retries,
    )
    byok = x_anthropic_key is not None

    def event_stream():
        # Sayım deseni generation.generate_stream ile birebir — bkz. oradaki gerekçe.
        reserved = 0
        started = False
        full_text = ""
        try:
            for kind, payload in generate_aydinlatma_envanter_stream(
                sections, boilerplate, profile, provider=provider, max_tokens=settings.max_tokens,
            ):
                if kind == "grounding":
                    yield _sse("grounding", [g.model_dump(by_alias=True) for g in payload])
                elif kind == "delta":
                    if not started:
                        started = True
                        # Uyum sinyali (aynı işlemde, rezervasyon commit'inden önce).
                        GeneratedDocumentRepository(session).record(identity.org_id, DocType.aydinlatma)
                        reserved = reserve_generation_usage(
                            session,
                            settings,
                            identity.org_id,
                            model=settings.default_model,
                            byok=byok,
                        )
                    full_text += payload
                    yield _sse("delta", {"text": payload})
                elif kind == "done":
                    yield _sse("done", payload)
                    usage = payload.get("usage")
                    settle_generation_usage(
                        session,
                        settings,
                        identity.org_id,
                        model=payload.get("model") or settings.default_model,
                        input_tokens=usage["inputTokens"] if usage else 0,
                        output_tokens=usage["outputTokens"] if usage else 0,
                        byok=byok,
                        reserved_micros=reserved,
                    )
                    if payload.get("stopReason") == "max_tokens":
                        # Kesik belge tam puanla resmi kayit olarak SAKLANMAZ.
                        _log.warning(
                            "aydinlatma uretimi kesildi (max_tokens): org=%s doc_type=aydinlatma",
                            identity.org_id,
                        )
                        yield _sse("warning", {
                            "code": "truncated_max_tokens",
                            "message": (
                                "Belge, model çıktı uzunluğu sınırına takıldığı için eksik "
                                "kaldı ve KAYDEDİLMEDİ. Kapsamı (hedef grup/bölüm sayısını) "
                                "daraltıp yeniden deneyin."
                            ),
                        })
                    else:
                        try:
                            _store_generated_document(
                                session, identity.org_id, client_id, sections, ensure_disclaimer(full_text)
                            )
                        except Exception as store_err:  # best-effort; uretimi bozma
                            # PII sizintisi riski: SQL exception string'i belge icerigini (musvekkil PII)
                            # tasiyabilir, capture_exception frame local'lerini (content, statuses) Sentry'ye
                            # serilestirir. Bu yuzden yalniz exception TURU + org_id loglanir; string/traceback YOK.
                            _log.error(
                                "belge saklama basarisiz (org=%s): %s",
                                identity.org_id, type(store_err).__name__,
                            )
        except Exception as e:
            if not started:
                idempotency.release(identity.org_id, idempotency_key)
            _log.exception("aydınlatma akış hatası (org=%s)", identity.org_id)
            capture_exception(e)
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


@router.post("/{client_id}/aydinlatma/docx")
def docx(
    client_id: uuid.UUID,
    body: DocxIn,
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(tenant_session),
) -> Response:
    if ClientRepository(session).get(identity.org_id, client_id) is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")
    data = render_docx(body.text, body.title or "Aydınlatma Metni")
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="aydinlatma.docx"'},
    )


@router.get("/{client_id}/documents", response_model=ClientDocumentsOut, response_model_by_alias=True)
def list_documents(
    client_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(tenant_session),
) -> ClientDocumentsOut:
    if ClientRepository(session).get(identity.org_id, client_id) is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")
    rows = ClientDocumentRepository(session).list_for_client(identity.org_id, client_id)
    return ClientDocumentsOut(documents=[ClientDocumentMetaOut.model_validate(r, from_attributes=True) for r in rows])


@router.get("/{client_id}/documents/{document_id}", response_model=ClientDocumentOut, response_model_by_alias=True)
def get_document(
    client_id: uuid.UUID,
    document_id: uuid.UUID,
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(tenant_session),
) -> ClientDocumentOut:
    if ClientRepository(session).get(identity.org_id, client_id) is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")
    row = ClientDocumentRepository(session).get(identity.org_id, client_id, document_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Belge bulunamadı.")
    return ClientDocumentOut.model_validate(row, from_attributes=True)
