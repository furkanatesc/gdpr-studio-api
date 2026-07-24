from __future__ import annotations

import uuid

import app.config as config_module
import app.idempotency as idem
import app.modules.cerez as cerezmod
import app.redis_client as rc
from app.auth.identity import Identity
from app.models import GeneratedDocument
from app.repositories import ClientRepository, GeneratedDocumentRepository
from legal_core.models import DocType

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


def test_cerez_generate_hala_8000_max_tokens_ile_cagirir(db_session, monkeypatch):
    """Regresyon kilidi: cerez kayit'in 32000 tavanindan ETKILENMEMELI, hala 8000
    kullanmali (kayit'e ozel tavan yalniz doc_type='kayit' icin gecerli)."""
    _managed_billing_settings()
    captured = {}

    def _capture_stream(req, **kw):
        captured["max_tokens"] = kw.get("max_tokens")
        yield from _fake_stream()

    monkeypatch.setattr(cerezmod, "generate_document_stream", _capture_stream)
    cid = _make_client(db_session)

    resp = _generate(db_session, cid)
    _consume(resp)

    assert captured["max_tokens"] == 8000


class _FakeRedis:
    """set(nx, ex) + delete destekleyen minimum sahte Redis (TTL simüle edilmez)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0

    def ping(self) -> bool:
        return True


def _use_fake_redis(monkeypatch) -> _FakeRedis:
    fake = _FakeRedis()
    monkeypatch.setattr(idem, "get_redis", lambda: fake)
    monkeypatch.setattr(rc, "get_redis", lambda: fake)
    return fake


def test_cerez_generate_uyari_donedan_once_gelir(db_session, monkeypatch):
    """Borc #1: 'warning' 'done'dan ONCE gelmeli; done payload'inda ek sigorta alanlari olmali."""
    import json

    _managed_billing_settings()
    monkeypatch.setattr(cerezmod, "generate_document_stream", _fake_stream_truncated)
    cid = _make_client(db_session)

    resp = _generate(db_session, cid)
    body = _consume(resp)

    assert "event: warning" in body and "event: done" in body
    assert body.index("event: warning") < body.index("event: done")

    done_line = [ln for ln in body.splitlines() if ln.startswith("data: ")][-1]
    done_payload = json.loads(done_line[len("data: "):])
    assert done_payload["incomplete"] is True
    assert done_payload["warningMessage"]


def test_cerez_generate_max_tokensta_uyum_kaydi_geri_alinir(db_session, monkeypatch):
    """Borc #2: kesmede generated_documents satiri SAYILMAMALI; org'un ONCEKI gecerli
    kaydi ETKILENMEMELI."""
    _managed_billing_settings()
    GeneratedDocumentRepository(db_session).record(IDENT.org_id, DocType.cerez)
    db_session.commit()

    monkeypatch.setattr(cerezmod, "generate_document_stream", _fake_stream_truncated)
    cid = _make_client(db_session)

    resp = _generate(db_session, cid)
    _consume(resp)

    rows = db_session.query(GeneratedDocument).filter_by(doc_type="cerez").all()
    assert len(rows) == 1


def _fake_stream_with_stop_reason(stop_reason):
    def _f(*a, **k):
        yield "grounding", []
        yield "delta", "Cerez politikasi metni"
        yield "done", {
            "model": "claude-x",
            "usage": {"inputTokens": 10, "outputTokens": 20},
            "stopReason": stop_reason,
        }

    return _f


def test_cerez_generate_baglam_penceresi_asildiginda_saklanmaz(db_session, monkeypatch):
    """Borc #3: model_context_window_exceeded da kesme sayilmali."""
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(
        cerezmod, "generate_document_stream",
        _fake_stream_with_stop_reason("model_context_window_exceeded"),
    )
    cid = _make_client(db_session)

    resp = _generate(db_session, cid)
    body = _consume(resp)

    assert "event: warning" in body
    assert db_session.query(ClientDocument).filter_by(client_id=cid).count() == 0
    assert db_session.query(GeneratedDocument).filter_by(doc_type="cerez").count() == 0


def test_cerez_generate_refusal_saklanmaz_ve_farkli_mesaj_gosterilir(db_session, monkeypatch):
    """Borc #3: refusal SAKLANMAZ ama mesaji uzunluk-kesme mesajindan FARKLI olmali."""
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(
        cerezmod, "generate_document_stream",
        _fake_stream_with_stop_reason("refusal"),
    )
    cid = _make_client(db_session)

    resp = _generate(db_session, cid)
    body = _consume(resp)

    assert "event: warning" in body
    assert "generation_refused" in body
    assert "truncated_output_limit" not in body
    assert db_session.query(ClientDocument).filter_by(client_id=cid).count() == 0
    assert db_session.query(GeneratedDocument).filter_by(doc_type="cerez").count() == 0


def test_cerez_generate_end_turn_saklanir_regresyon_kilidi(db_session, monkeypatch):
    """Regresyon kilidi: stopReason='end_turn' -> belge HALA saklanir."""
    from app.models import ClientDocument

    _managed_billing_settings()
    monkeypatch.setattr(
        cerezmod, "generate_document_stream",
        _fake_stream_with_stop_reason("end_turn"),
    )
    cid = _make_client(db_session)

    resp = _generate(db_session, cid)
    body = _consume(resp)

    assert "event: warning" not in body
    rows = db_session.query(ClientDocument).filter_by(client_id=cid).all()
    assert len(rows) == 1
    assert db_session.query(GeneratedDocument).filter_by(doc_type="cerez").count() == 1


def test_cerez_generate_kesmede_idempotency_kilidi_birakilir(db_session, monkeypatch):
    """Borc #4: kesmede idempotency kilidi BIRAKILMALI."""
    _managed_billing_settings()
    fake = _use_fake_redis(monkeypatch)
    monkeypatch.setattr(cerezmod, "generate_document_stream", _fake_stream_truncated)
    cid = _make_client(db_session)

    resp = _generate(db_session, cid, idempotency_key="cerez-kesme-1")
    _consume(resp)

    assert fake.store == {}


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
