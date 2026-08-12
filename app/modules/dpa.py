# app/modules/dpa.py
"""DPA (Veri Isleyen Sozlesmesi) — muvekkil envanterinden isleyene aktarilan kapsamdan uretim/docx.

dpia.py'nin generate/docx uclarini izler; ek olarak isleyen kapsam cozumu (prepare) sunar.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date
from functools import partial

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from legal_core.document_text import DocumentTextError, extract_text
from legal_core.dpa_review import DPA_CHECKLIST, ReviewContext, ReviewParseError, review_dpa
from legal_core.dpa_scope import distinct_aktarim_adlari, resolve_dpa_scope
from legal_core.generate import generate_dpa_envanter_stream
from legal_core.models import DocType, ProcessorInfo
from legal_core.prompt import ensure_disclaimer
from legal_core.provider import AnthropicProvider
from legal_core.scoring import dpa_completeness_score

from .. import idempotency
from ..audit import record_audit
from ..auth.identity import Identity, get_current_identity
from ..auth.tenant_session import set_org_context, tenant_session
from ..billing.quota import (
    enforce_cost_budget,
    enforce_generation_quota,
    record_cost_only,
    release_generation_document,
    reserve_generation_usage,
    settle_generation_usage,
)
from ..config import get_settings
from ..docx_export import render_styled_docx
from ..observability import capture_exception
from ..redis_client import generate_rate_limit
from ..repositories import (
    ClientProcessorRepository,
    ClientRepository,
    GeneratedDocumentRepository,
    PostgresBusinessRuleRepository,
    PostgresMeasureRepository,
    PostgresProcessRepository,
)
from .document_store import client_profile, store_client_document
from .generation import _claim_idempotency, _resolve_api_key, _sse, classify_incomplete_stop_reason

router = APIRouter(prefix="/api/clients", tags=["dpa"])
_log = logging.getLogger("app.dpa")

MAX_REVIEW_CHARS = 200_000


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class DocxIn(_Camel):
    text: str
    title: str | None = None
    processor_id: uuid.UUID | None = None


class DpaPrepareIn(_Camel):
    processor_id: uuid.UUID


class DpaPrepareOut(_Camel):
    eslesen_surec_sayisi: int
    kategoriler: list[str]
    veri_turleri: list[str]
    amaclar: list[str]
    saklama_sureleri: list[str]
    teknik_tedbirler: list[str]
    idari_tedbirler: list[str]


class DpaGenerateIn(_Camel):
    processor_id: uuid.UUID


class ReviewFindingOut(_Camel):
    madde_id: str
    baslik: str
    kvkk_ref: str
    kirmizi_bayrak: bool
    durum: str
    alinti: str
    gerekce: str
    oneri: str


class ReviewResultOut(_Camel):
    bulgular: list[ReviewFindingOut]
    uygun: int
    eksik: int
    yetersiz: int
    kirmizi_bayrak: int
    disclaimer: str


def _require_client(session: Session, org_id, client_id) -> None:
    if ClientRepository(session).get(org_id, client_id) is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")


def _load_scope_and_processor(session, org_id, client_id, processor_id):
    row = ClientProcessorRepository(session).get(org_id, client_id, processor_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Veri işleyen bulunamadı.")
    records = PostgresProcessRepository(session).client_processes(client_id)
    scope = resolve_dpa_scope(records, list(row.aktarim_aliases or []))
    if not scope.eslesen_surecler:
        raise HTTPException(
            status_code=422,
            detail="Bu işleyene aktarılan hiçbir süreç yok; DPA kapsamı boş.")
    processor = ProcessorInfo(
        ad=row.ad, unvan=row.unvan, adres=row.adres, yetkili_kisi=row.yetkili_kisi,
        iletisim=row.iletisim, vergi_dairesi_no=row.vergi_dairesi_no,
        yurt_disi=row.yurt_disi, alt_isleyen_var=row.alt_isleyen_var,
        aktarim_aliases=list(row.aktarim_aliases or []))
    return scope, processor, row


def _detect_kind(filename: str) -> str:
    name = (filename or "").lower()
    if name.endswith(".docx"):
        return "docx"
    if name.endswith(".pdf"):
        return "pdf"
    raise HTTPException(status_code=422, detail="Yalnızca .docx ve .pdf desteklenir.")


def _build_review_context(session, org_id, client_id, processor_id):
    client = ClientRepository(session).get(org_id, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")
    prof = client_profile(client)
    records = PostgresProcessRepository(session).client_processes(client_id)
    isleyen_adi = None
    if processor_id is not None:
        row = ClientProcessorRepository(session).get(org_id, client_id, processor_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Veri işleyen bulunamadı.")
        isleyen_adi = row.unvan or row.ad
        scope = resolve_dpa_scope(records, list(row.aktarim_aliases or []))
        kategoriler = scope.kategoriler
        aktarim_adlari = list(row.aktarim_aliases or [])
    else:
        aktarim_adlari = distinct_aktarim_adlari(records)
        kategoriler = []
        for r in records:
            for k in r.kategoriler:
                if k and k not in kategoriler:
                    kategoriler.append(k)
    yurt_disi = any("yurt" in a.lower() or "dış" in a.lower() for a in aktarim_adlari)
    return ReviewContext(
        veri_sorumlusu=prof.unvan or prof.ad, isleyen_adi=isleyen_adi,
        yurt_disi=yurt_disi, aktarim_adlari=aktarim_adlari, kategoriler=kategoriler,
    )


@router.post("/{client_id}/dpa/prepare", response_model=DpaPrepareOut, response_model_by_alias=True)
def prepare(
    client_id: uuid.UUID,
    body: DpaPrepareIn,
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(tenant_session),
) -> DpaPrepareOut:
    _require_client(session, identity.org_id, client_id)
    scope, _processor, _row = _load_scope_and_processor(session, identity.org_id, client_id, body.processor_id)
    return DpaPrepareOut(
        eslesen_surec_sayisi=len(scope.eslesen_surecler),
        kategoriler=scope.kategoriler,
        veri_turleri=scope.veri_turleri,
        amaclar=scope.amaclar,
        saklama_sureleri=scope.saklama_sureleri,
        teknik_tedbirler=scope.teknik_tedbirler,
        idari_tedbirler=scope.idari_tedbirler,
    )


@router.post("/{client_id}/dpa/generate", dependencies=[Depends(generate_rate_limit)])
def generate(
    client_id: uuid.UUID,
    body: DpaGenerateIn,
    session: Session = Depends(tenant_session),
    identity: Identity = Depends(enforce_generation_quota),
    x_anthropic_key: str | None = Header(default=None, alias="X-Anthropic-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> StreamingResponse:
    """Muvekkil envanterinden, isleyene aktarilan kapsamdan DPA taslagi akisi (SSE)."""
    settings = get_settings()

    client = ClientRepository(session).get(identity.org_id, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")

    scope, processor, _row = _load_scope_and_processor(
        session, identity.org_id, client_id, body.processor_id
    )

    api_key = _resolve_api_key(x_anthropic_key)
    _claim_idempotency(identity, idempotency_key)

    prof = client_profile(client)
    measures = PostgresMeasureRepository(session).all_measures()
    rules = PostgresBusinessRuleRepository(session).business_rules("dpa")
    cap = settings.process_cap
    dpa_max_tokens = settings.max_tokens_for("dpa")
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
        generated_doc_id: uuid.UUID | None = None
        try:
            for kind, payload in generate_dpa_envanter_stream(
                scope, prof, processor, measures, rules, provider=provider,
                max_tokens=dpa_max_tokens, process_cap=cap,
            ):
                if kind == "grounding":
                    yield _sse("grounding", [g.model_dump(by_alias=True) for g in payload])
                elif kind == "delta":
                    if not started:
                        started = True
                        generated_doc_id = GeneratedDocumentRepository(session).record(
                            identity.org_id, DocType.dpa, identity.user_id
                        )
                        reserved = reserve_generation_usage(
                            session, settings, identity.org_id,
                            model=settings.default_model, byok=byok,
                            max_tokens=dpa_max_tokens,
                        )
                    full_text += payload
                    yield _sse("delta", {"text": payload})
                elif kind == "done":
                    incomplete_kind = classify_incomplete_stop_reason(payload.get("stopReason"))
                    warn_code, warn_message = None, None
                    if incomplete_kind == "truncated":
                        warn_code = "truncated_output_limit"
                        warn_message = (
                            "Belge, model çıktı/bağlam sınırına takıldığı için eksik "
                            "kaldı ve KAYDEDİLMEDİ. Envanterdeki süreç sayısını daraltıp "
                            "yeniden deneyin."
                        )
                    elif incomplete_kind == "refusal":
                        warn_code = "generation_refused"
                        warn_message = (
                            "Model bu içeriği üretmeyi REDDETTİ; bu bir uzunluk sorunu "
                            "değildir, kapsamı daraltmak yardımcı olmaz. İçeriği gözden "
                            "geçirip tekrar deneyin."
                        )
                    if warn_code:
                        # Kesik/reddedilen belge tam puanla resmi DPA kaydi olarak SAKLANMAZ.
                        _log.warning(
                            "dpa uretimi tamamlanamadi (stop_reason=%s): org=%s doc_type=dpa",
                            payload.get("stopReason"), identity.org_id,
                        )
                        # Uyari, 'done'dan ONCE yayinlanir (bkz. generation.py gerekcesi).
                        yield _sse("warning", {"code": warn_code, "message": warn_message})
                        payload = {**payload, "incomplete": True, "warningMessage": warn_message}
                    yield _sse("done", payload)
                    usage = payload.get("usage")
                    settle_generation_usage(
                        session, settings, identity.org_id,
                        model=payload.get("model") or settings.default_model,
                        input_tokens=usage["inputTokens"] if usage else 0,
                        output_tokens=usage["outputTokens"] if usage else 0,
                        byok=byok, reserved_micros=reserved,
                    )
                    if warn_code:
                        try:
                            if generated_doc_id is not None:
                                set_org_context(session, identity.org_id)
                                GeneratedDocumentRepository(session).discard(
                                    identity.org_id, generated_doc_id
                                )
                                session.commit()
                                # Belge saklanmadi -> reserve'in doc_count artisini da geri al.
                                release_generation_document(session, identity.org_id)
                        except Exception as discard_err:  # best-effort; uyariyi bozma
                            _log.error(
                                "generated_documents geri alma basarisiz (org=%s): %s",
                                identity.org_id, type(discard_err).__name__,
                            )
                        idempotency.release(identity.org_id, idempotency_key)
                    else:
                        try:
                            set_org_context(session, identity.org_id)
                            record_audit(
                                session, org_id=identity.org_id, action="document.generated",
                                actor_user_id=identity.user_id, target_type="document",
                                target_id=DocType.dpa,
                            )
                            store_client_document(
                                session, identity.org_id, client_id, "dpa",
                                (processor.unvan or processor.ad),
                                ensure_disclaimer(full_text), dpa_completeness_score(scope),
                            )
                        except Exception as store_err:  # best-effort; PII'siz log
                            _log.error(
                                "dpa saklama basarisiz (org=%s): %s",
                                identity.org_id, type(store_err).__name__,
                            )
        except Exception as e:
            if not started:
                idempotency.release(identity.org_id, idempotency_key)
            _log.exception("dpa akis hatasi (org=%s)", identity.org_id)
            capture_exception(e)
            yield _sse("error", {"detail": "Belge üretilemedi; lütfen tekrar deneyin."})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/{client_id}/dpa/docx")
def docx(
    client_id: uuid.UUID,
    body: DocxIn,
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(tenant_session),
) -> Response:
    client = ClientRepository(session).get(identity.org_id, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")
    prof = client_profile(client)
    veri_isleyen = None
    if body.processor_id is not None:
        row = ClientProcessorRepository(session).get(identity.org_id, client_id, body.processor_id)
        veri_isleyen = row.unvan if row else None
    data = render_styled_docx(
        body.text,
        "dpa",
        {
            "veri_sorumlusu": prof.unvan or prof.ad,
            "veri_isleyen": veri_isleyen,
            "tarih": date.today().strftime("%d.%m.%Y"),
            "versiyon": "Taslak",
        },
    )
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="dpa.docx"'},
    )


@router.post("/{client_id}/dpa/review", response_model=ReviewResultOut,
             response_model_by_alias=True, dependencies=[Depends(generate_rate_limit)])
async def review(
    client_id: uuid.UUID,
    text: str | None = Form(default=None),
    processor_id: uuid.UUID | None = Form(default=None, alias="processorId"),
    file: UploadFile | None = File(default=None),
    identity: Identity = Depends(enforce_cost_budget),
    session: Session = Depends(tenant_session),
    x_anthropic_key: str | None = Header(default=None, alias="X-Anthropic-Key"),
) -> ReviewResultOut:
    """Yüklenen DPA metnini KVKK m.12 kontrol listesine göre analiz eder (kalıcı değil)."""
    settings = get_settings()
    _require_client(session, identity.org_id, client_id)

    if file is not None and file.filename:
        kind = _detect_kind(file.filename)
        try:
            source_text = extract_text(await file.read(), kind)
        except DocumentTextError as e:
            _log.warning(
                "dpa-incele belge okunamadi (org=%s): %s", identity.org_id, type(e).__name__)
            raise HTTPException(
                status_code=422,
                detail="Belge okunamadı; dosya bozuk olabilir. Metni elle yapıştırmayı deneyin.",
            ) from e
    else:
        source_text = text or ""
    if not source_text.strip():
        raise HTTPException(
            status_code=422,
            detail="İncelenecek metin veya dosya gerekli; belgeden metin çıkarılamadıysa "
                   "metni elle yapıştırın.")
    if len(source_text) > MAX_REVIEW_CHARS:
        raise HTTPException(
            status_code=422,
            detail="Belge çok büyük; en fazla ~200.000 karakter incelenebilir.")

    context = _build_review_context(session, identity.org_id, client_id, processor_id)
    api_key = _resolve_api_key(x_anthropic_key)
    byok = x_anthropic_key is not None
    provider = AnthropicProvider(
        api_key, model=settings.default_model,
        timeout_s=settings.anthropic_timeout_s, max_retries=settings.anthropic_max_retries,
    )
    try:
        result = await run_in_threadpool(
            partial(review_dpa, source_text, context, provider=provider)
        )
    except ReviewParseError as e:
        capture_exception(e)
        raise HTTPException(status_code=502, detail="Analiz biçimlendirilemedi; tekrar deneyin.") from e

    usage = provider.last_result
    record_cost_only(
        session, settings, identity.org_id, model=settings.default_model,
        input_tokens=usage.input_tokens if usage else 0,
        output_tokens=usage.output_tokens if usage else 0, byok=byok,
    )

    by_id = {it.id: it for it in DPA_CHECKLIST}
    out = [
        ReviewFindingOut(
            madde_id=f.madde_id,
            baslik=by_id[f.madde_id].baslik if f.madde_id in by_id else f.madde_id,
            kvkk_ref=by_id[f.madde_id].kvkk_ref if f.madde_id in by_id else "",
            kirmizi_bayrak=by_id[f.madde_id].kirmizi_bayrak if f.madde_id in by_id else False,
            durum=f.durum, alinti=f.alinti, gerekce=f.gerekce, oneri=f.oneri,
        )
        for f in result.bulgular
    ]
    return ReviewResultOut(
        bulgular=out, uygun=result.uygun, eksik=result.eksik, yetersiz=result.yetersiz,
        kirmizi_bayrak=result.kirmizi_bayrak, disclaimer=result.disclaimer,
    )
