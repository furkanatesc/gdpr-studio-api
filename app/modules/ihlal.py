# app/modules/ihlal.py
"""İhlal bildirimi — iki eşik testi (kurul/ilgili kişi) + kurul/ilgili kişi metni üretimi.

dpia.py'nin prepare/generate/docx desenini izler. KALICILIK YOK: üretilen metin
ClientDocument'a yazılmaz (migration/yeni tablo yok) — yalnız akış + docx export.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from legal_core.generate import generate_ihlal_stream
from legal_core.ihlal import IhlalOlay, evaluate_ihlal_bildirim
from legal_core.models import DocType
from legal_core.provider import AnthropicProvider

from .. import idempotency
from ..audit import record_audit
from ..auth.identity import Identity, get_current_identity
from ..auth.tenant_session import set_org_context, tenant_session
from ..billing.quota import (
    enforce_generation_quota,
    release_generation_document,
    reserve_generation_usage,
    settle_generation_usage,
)
from ..config import get_settings
from ..docx_export import render_styled_docx
from ..observability import capture_exception
from ..redis_client import generate_rate_limit
from ..repositories import (
    ClientRepository,
    GeneratedDocumentRepository,
    PostgresBusinessRuleRepository,
    PostgresMeasureRepository,
    PostgresProcessRepository,
)
from .document_store import client_profile
from .generation import _claim_idempotency, _resolve_api_key, _sse, classify_incomplete_stop_reason

router = APIRouter(prefix="/api/clients", tags=["ihlal"])
_log = logging.getLogger("app.ihlal")


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class IhlalOlayIn(_Camel):
    tespit: datetime
    tur: str
    etkilenen_indeksler: list[int] = []
    kimlik_finansal: bool = False
    sifreli: bool = False
    kisi_sayisi: int = 0
    nasil: str = ""
    onlemler: str = ""


class IhlalPrepareIn(IhlalOlayIn):
    pass


class IhlalPrepareOut(_Camel):
    kurul_gerekli: bool
    ilgili_kisi_gerekli: bool
    ilgili_kisi_muafiyet: bool
    ilgili_kisi_sinyaller: list[str]
    ozel_nitelikli_var: bool
    saat_kalan: float | None
    sure_asildi: bool


class IhlalGenerateIn(IhlalOlayIn):
    bildirim_turu: str  # "kurul" | "ilgili_kisi"


class DocxIn(_Camel):
    text: str
    title: str | None = None


def _olay_ve_kapsam(session: Session, client_id: uuid.UUID, body: IhlalOlayIn):
    records = PostgresProcessRepository(session).client_processes(client_id)
    if not records:
        raise HTTPException(status_code=422, detail="Envanterde süreç yok — önce envanter girin.")
    kategoriler: list[str] = []
    veri_turleri: list[str] = []
    for i in body.etkilenen_indeksler:
        if i < 0 or i >= len(records):
            raise HTTPException(
                status_code=422, detail="Seçilen süreç envanterde yok; envanter değişmiş olabilir."
            )
        for k in records[i].kategoriler:
            if k and k not in kategoriler:
                kategoriler.append(k)
        for v in records[i].veri_turleri:
            if v and v not in veri_turleri:
                veri_turleri.append(v)
    olay = IhlalOlay(
        tespit=body.tespit,
        tur=body.tur,
        etkilenen_kategoriler=kategoriler,
        ozel_nitelikli_secili=False,
        kimlik_finansal=body.kimlik_finansal,
        sifreli=body.sifreli,
        kisi_sayisi=body.kisi_sayisi,
        nasil=body.nasil,
        onlemler=body.onlemler,
    )
    return olay, kategoriler, veri_turleri


@router.post("/{client_id}/ihlal/prepare", response_model=IhlalPrepareOut, response_model_by_alias=True)
def prepare(
    client_id: uuid.UUID,
    body: IhlalPrepareIn,
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(tenant_session),
) -> IhlalPrepareOut:
    client = ClientRepository(session).get(identity.org_id, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")
    olay, _kategoriler, _veri_turleri = _olay_ve_kapsam(session, client_id, body)
    v = evaluate_ihlal_bildirim(olay, simdi=datetime.now())
    return IhlalPrepareOut(
        kurul_gerekli=v.kurul_gerekli,
        ilgili_kisi_gerekli=v.ilgili_kisi_gerekli,
        ilgili_kisi_muafiyet=v.ilgili_kisi_muafiyet,
        ilgili_kisi_sinyaller=v.ilgili_kisi_sinyaller,
        ozel_nitelikli_var=v.ozel_nitelikli_var,
        saat_kalan=v.saat_kalan,
        sure_asildi=v.sure_asildi,
    )


@router.post("/{client_id}/ihlal/generate", dependencies=[Depends(generate_rate_limit)])
def generate(
    client_id: uuid.UUID,
    body: IhlalGenerateIn,
    session: Session = Depends(tenant_session),
    identity: Identity = Depends(enforce_generation_quota),
    x_anthropic_key: str | None = Header(default=None, alias="X-Anthropic-Key"),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> StreamingResponse:
    """İhlal bildirimi (kurul | ilgili kişi) akışı (SSE). KALICILIK YOK."""
    settings = get_settings()

    client = ClientRepository(session).get(identity.org_id, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")

    bildirim_turu = body.bildirim_turu
    if bildirim_turu not in ("kurul", "ilgili_kisi"):
        raise HTTPException(status_code=422, detail="bildirimTuru 'kurul' veya 'ilgili_kisi' olmalı.")

    olay, kategoriler, veri_turleri = _olay_ve_kapsam(session, client_id, body)

    api_key = _resolve_api_key(x_anthropic_key)
    _claim_idempotency(identity, idempotency_key)

    prof = client_profile(client)
    measures = PostgresMeasureRepository(session).all_measures()
    rules = PostgresBusinessRuleRepository(session).business_rules("ihlal")
    ihlal_max_tokens = settings.max_tokens_for("ihlal")
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
        generated_doc_id: uuid.UUID | None = None
        try:
            for kind, payload in generate_ihlal_stream(
                olay, prof, kategoriler, veri_turleri, measures, rules, bildirim_turu,
                provider=provider, max_tokens=ihlal_max_tokens,
            ):
                if kind == "delta":
                    if not started:
                        started = True
                        generated_doc_id = GeneratedDocumentRepository(session).record(
                            identity.org_id, DocType.ihlal, identity.user_id
                        )
                        reserved = reserve_generation_usage(
                            session, settings, identity.org_id,
                            model=settings.default_model, byok=byok,
                            max_tokens=ihlal_max_tokens,
                        )
                    yield _sse("delta", {"text": payload})
                elif kind == "done":
                    incomplete_kind = classify_incomplete_stop_reason(payload.get("stopReason"))
                    warn_code, warn_message = None, None
                    if incomplete_kind == "truncated":
                        warn_code = "truncated_output_limit"
                        warn_message = (
                            "Belge, model çıktı/bağlam sınırına takıldığı için eksik "
                            "kaldı ve KAYDEDİLMEDİ. Kapsamı daraltıp yeniden deneyin."
                        )
                    elif incomplete_kind == "refusal":
                        warn_code = "generation_refused"
                        warn_message = (
                            "Model bu içeriği üretmeyi REDDETTİ; bu bir uzunluk sorunu "
                            "değildir, kapsamı daraltmak yardımcı olmaz. İçeriği gözden "
                            "geçirip tekrar deneyin."
                        )
                    if warn_code:
                        _log.warning(
                            "ihlal uretimi tamamlanamadi (stop_reason=%s): org=%s doc_type=ihlal",
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
                        # Başarı dalı: KALICILIK YOK — ClientDocument'a yazılmaz; yalniz audit.
                        try:
                            set_org_context(session, identity.org_id)
                            record_audit(
                                session, org_id=identity.org_id, action="document.generated",
                                actor_user_id=identity.user_id, target_type="document",
                                target_id=DocType.ihlal,
                            )
                            session.commit()
                        except Exception as audit_err:  # best-effort; basariyi bozma
                            _log.error(
                                "document.generated audit basarisiz (org=%s): %s",
                                identity.org_id, type(audit_err).__name__,
                            )
        except Exception as e:
            if not started:
                idempotency.release(identity.org_id, idempotency_key)
            _log.exception("ihlal akis hatasi (org=%s)", identity.org_id)
            capture_exception(e)
            yield _sse("error", {"detail": "Belge üretilemedi; lütfen tekrar deneyin."})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )


@router.post("/{client_id}/ihlal/docx")
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
    data = render_styled_docx(
        body.text,
        "ihlal",
        {
            "veri_sorumlusu": prof.unvan or prof.ad,
            "tarih": date.today().strftime("%d.%m.%Y"),
            "versiyon": "Taslak",
        },
    )
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": 'attachment; filename="ihlal.docx"'},
    )
