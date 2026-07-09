"""Generation kancası: başarılı üretim generated_documents'a satır yazar; hata → yazmaz."""

import app.config as config_module
import app.modules.generation as genmod
from app.models import GeneratedDocument
from legal_core.models import GenerateResponse, Usage


def _managed_billing_settings():
    # billing açık → record_generation_usage commit eder (kanca aynı işlemde persist olur)
    config_module._settings = config_module.Settings(
        _env_file=None,
        managed_anthropic_api_key="sk-managed-test",
        allowed_origins="http://localhost:3000",
        redis_url="",
        stripe_secret_key="sk_test_x",
        stripe_webhook_secret="whsec_x",
    )


def _fake_response():
    return GenerateResponse(
        text="metin", grounding=[], model="claude-sonnet-4-6",
        disclaimer="d", usage=Usage(input_tokens=100, output_tokens=200),
    )


def test_successful_generation_records_document(client, db_session, monkeypatch):
    _managed_billing_settings()
    monkeypatch.setattr(genmod, "generate_document", lambda *a, **k: _fake_response())
    r = client.post("/api/generate", json={"type": "aydinlatma"})
    assert r.status_code == 200
    rows = db_session.query(GeneratedDocument).all()
    assert len(rows) == 1
    assert rows[0].doc_type == "aydinlatma"
    assert str(rows[0].org_id) == "00000000-0000-0000-0000-000000000002"  # _DEV_IDENTITY org


def test_failed_generation_records_no_document(client, db_session, monkeypatch):
    _managed_billing_settings()

    def _boom(*a, **k):
        raise RuntimeError("model patladı")

    monkeypatch.setattr(genmod, "generate_document", _boom)
    r = client.post("/api/generate", json={"type": "aydinlatma"})
    assert r.status_code == 502
    assert db_session.query(GeneratedDocument).count() == 0


def test_streaming_generation_records_document(client, db_session, monkeypatch):
    _managed_billing_settings()

    def _fake_stream(*a, **k):
        yield "grounding", []
        yield "delta", "me"
        yield "done", {"model": "claude-sonnet-4-6", "usage": {"inputTokens": 10, "outputTokens": 20}}

    monkeypatch.setattr(genmod, "generate_document_stream", _fake_stream)
    with client.stream("POST", "/api/generate/stream", json={"type": "cerez"}) as r:
        assert r.status_code == 200
        body = "".join(r.iter_text())
    assert "event: done" in body
    rows = db_session.query(GeneratedDocument).all()
    assert len(rows) == 1
    assert rows[0].doc_type == "cerez"
