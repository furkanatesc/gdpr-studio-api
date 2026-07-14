"""Akış (SSE) üretiminde faturalandırma bütünlüğü — H1-1 (mimari review P1).

Kaçak: kayıt yalnız 'done' dalında yapılırsa, istemci 'done'dan hemen önce bağlantıyı
koparınca üretim HİÇ sayılmaz → ücretsiz doküman tavanı ve managed maliyet bütçesi
süresiz atlanır. Kopma anında üretecin `finally`'si ancak çöp toplamada çalışır ve o an
istek oturumu kapanmış olabilir → oraya yazmak da güvenilir değildir.

Çözüm: sayım ilk delta'da (model kesin çağrıldı, oturum canlı) REZERVE edilir; 'done'
gelince gerçek kullanımla mahsuplaşır. Kopan istemci rezervasyonu üstlenir.
"""

from __future__ import annotations

import asyncio
import uuid

import app.config as config_module
import app.modules.generation as genmod
from app.auth.identity import Identity
from app.billing.pricing import cost_micros
from app.models import GeneratedDocument, UsageCounter
from legal_core import GenerateRequest

IDENT = Identity(
    user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    org_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    role="yonetici",
    email="dev@kvkkyonetim.local",
)


def _managed_billing_settings():
    # billing açık (Stripe anahtarları) + managed model anahtarı → gerçek sayım yolu çalışır
    config_module._settings = config_module.Settings(
        _env_file=None,
        managed_anthropic_api_key="sk-managed-test",
        allowed_origins="http://localhost:3000",
        redis_url="",
        stripe_secret_key="sk_test_x",
        stripe_webhook_secret="whsec_x",
    )
    return config_module._settings


def _fake_stream_factory(settings):
    def _fake_stream(*a, **k):
        yield "grounding", []
        yield "delta", "Aydınlatma"
        yield "delta", " metni"
        yield "done", {
            "model": settings.default_model,
            "usage": {"inputTokens": 1000, "outputTokens": 2000},
        }

    return _fake_stream


def _stream_response(db_session, *, doc_type="aydinlatma", byok=None):
    return genmod.generate_stream(
        GenerateRequest(type=doc_type),
        session=db_session,
        identity=IDENT,
        x_anthropic_key=byok,
    )


def _consume(response, *, events: int | None = None) -> None:
    """SSE üretecini tüket. events verilirse o kadar olaydan sonra kopar (istemci disconnect)."""

    async def _run():
        it = response.body_iterator
        if events is None:
            async for _ in it:
                pass
            return
        for _ in range(events):
            await it.__anext__()
        await it.aclose()

    asyncio.run(_run())


def _counter(db_session) -> UsageCounter | None:
    return db_session.query(UsageCounter).one_or_none()


def test_stream_abort_before_done_still_counts_usage(db_session, monkeypatch):
    """İstemci ilk delta'dan sonra koparsa bile üretim sayılır (bypass kapalı)."""
    settings = _managed_billing_settings()
    monkeypatch.setattr(genmod, "generate_document_stream", _fake_stream_factory(settings))

    _consume(_stream_response(db_session), events=2)  # grounding + ilk delta, sonra kopar

    row = _counter(db_session)
    assert row is not None
    assert row.doc_count == 1  # ücretsiz tavan artık atlanamıyor
    # 'done' gelmediği için gerçek token bilinmiyor → en kötü durum rezervasyonu üstlenilir
    assert row.cost_micros == cost_micros(settings.default_model, 0, settings.max_tokens)
    assert db_session.query(GeneratedDocument).count() == 1


def test_stream_completion_settles_actual_cost_and_counts_once(db_session, monkeypatch):
    """Akış tamamlanınca: tek sayım + rezervasyon gerçek maliyetle mahsuplaşır."""
    settings = _managed_billing_settings()
    monkeypatch.setattr(genmod, "generate_document_stream", _fake_stream_factory(settings))

    _consume(_stream_response(db_session))

    row = _counter(db_session)
    assert row is not None
    assert row.doc_count == 1  # iki delta + done → tek sayım
    assert row.cost_micros == cost_micros(settings.default_model, 1000, 2000)
    assert row.input_tokens == 1000
    assert row.output_tokens == 2000
    assert db_session.query(GeneratedDocument).count() == 1


def test_stream_abort_before_first_delta_counts_nothing(db_session, monkeypatch):
    """Model hiç çağrılmadan (grounding'de) kopma → sayım yok; kullanıcı boşuna ödemez."""
    settings = _managed_billing_settings()
    monkeypatch.setattr(genmod, "generate_document_stream", _fake_stream_factory(settings))

    _consume(_stream_response(db_session), events=1)  # yalnız grounding

    assert _counter(db_session) is None
    assert db_session.query(GeneratedDocument).count() == 0


def test_stream_byok_counts_document_but_no_cost(db_session, monkeypatch):
    """BYOK: maliyet bizim değil → rezerve edilmez; doküman tavanı yine sayılır."""
    settings = _managed_billing_settings()
    monkeypatch.setattr(genmod, "generate_document_stream", _fake_stream_factory(settings))

    _consume(_stream_response(db_session, byok="sk-user-key"))

    row = _counter(db_session)
    assert row is not None
    assert row.doc_count == 1
    assert row.cost_micros == 0
