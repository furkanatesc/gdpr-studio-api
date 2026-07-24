from __future__ import annotations

import uuid

import app.config as config_module
import app.modules.cerez as cerezmod
from app.auth.identity import Identity
from app.repositories import ClientRepository

IDENT = Identity(
    user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    org_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    role="yonetici",
    email="dev@kvkkyonetim.local",
)


def _managed_billing_settings():
    config_module._settings = config_module.Settings(
        _env_file=None, managed_anthropic_api_key="sk-managed-test",
        allowed_origins="http://localhost:3000", redis_url="",
        stripe_secret_key="sk_test_x", stripe_webhook_secret="whsec_x",
    )


def _make_client(db_session):
    c = ClientRepository(db_session).create(IDENT.org_id, "Otel", "otel")
    db_session.commit()
    return c.id


def _fake_stream(*a, **k):
    yield "grounding", []
    yield "delta", "Cerez"
    yield "delta", " politikasi"
    yield "done", {"model": "claude-x", "usage": {"inputTokens": 10, "outputTokens": 20}}


def _consume(response) -> str:
    import asyncio

    async def _run():
        chunks = []
        async for chunk in response.body_iterator:
            chunks.append(chunk)
        return chunks

    return "".join(asyncio.run(_run()))


def _generate(db_session, client_id, **overrides):
    body = cerezmod.CerezGenerateIn(site="otel.com", tools="GA", cmp="yok", kategoriler=["Zorunlu çerezler"])
    kwargs = dict(session=db_session, identity=IDENT, x_anthropic_key=None, idempotency_key=None)
    kwargs.update(overrides)
    return cerezmod.generate(client_id=client_id, body=body, **kwargs)


def test_cerez_generate_musvekkil_yok_404(db_session, monkeypatch):
    _managed_billing_settings()
    monkeypatch.setattr(cerezmod, "generate_document_stream", _fake_stream)
    from fastapi import HTTPException

    try:
        _generate(db_session, uuid.uuid4())
    except HTTPException as e:
        assert e.status_code == 404
    else:
        raise AssertionError("404 bekleniyordu")


def _fake_stream_truncated(*a, **k):
    yield "grounding", []
    yield "delta", "Kesik cerez politikasi..."
    yield "done", {
        "model": "claude-x",
        "usage": {"inputTokens": 8000, "outputTokens": 8000},
        "stopReason": "max_tokens",
    }


def test_cerez_generate_max_tokensta_saklanmaz_ve_uyari_yayinlanir(db_session, monkeypatch):
    """Borc: kesik uretim (stop_reason=max_tokens) SAKLANMAMALI, istemci 'warning' alir."""
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(cerezmod, "generate_document_stream", _fake_stream_truncated)
    cid = _make_client(db_session)

    resp = _generate(db_session, cid)
    body = _consume(resp)

    assert "event: warning" in body
    assert "event: error" not in body
    rows = db_session.query(ClientDocument).filter_by(client_id=cid).all()
    assert len(rows) == 0


def test_cerez_generate_belgeyi_saklar_iki_puanla(db_session, monkeypatch):
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(cerezmod, "generate_document_stream", _fake_stream)
    cid = _make_client(db_session)

    resp = _generate(db_session, cid)
    _consume(resp)

    rows = db_session.query(ClientDocument).filter_by(client_id=cid).all()
    assert len(rows) == 1
    assert rows[0].doc_type == "cerez"
    assert "politikasi" in rows[0].content
    assert rows[0].title == "otel.com"          # site -> title
    # kimlik(1)+kategori(1)+arac(1)=3, cmp=yok -> 3/4
    assert rows[0].score_completeness == 0.75
    assert rows[0].score_compliance == 0.0      # org'da uyum statusu yok
