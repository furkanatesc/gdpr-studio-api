import uuid  # noqa: F401  (paralellik; gerekirse)

import app.config as config_module
import app.modules.generation as genmod
from legal_core.models import GenerateResponse, Usage


def _managed_billing_settings():
    # managed anahtar dolu (_resolve_api_key geçer) + billing açık (record no-op değil)
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


def test_generate_records_managed_args(client, db_session, monkeypatch):
    _managed_billing_settings()
    monkeypatch.setattr(genmod, "generate_document", lambda *a, **k: _fake_response())
    captured = {}
    monkeypatch.setattr(genmod, "record_generation_usage", lambda *a, **k: captured.update(k))
    r = client.post("/api/generate", json={"type": "aydinlatma"})
    assert r.status_code == 200
    assert captured["model"] == "claude-sonnet-4-6"
    assert captured["input_tokens"] == 100
    assert captured["output_tokens"] == 200
    assert captured["byok"] is False


def test_generate_records_byok_flag(client, db_session, monkeypatch):
    _managed_billing_settings()
    monkeypatch.setattr(genmod, "generate_document", lambda *a, **k: _fake_response())
    captured = {}
    monkeypatch.setattr(genmod, "record_generation_usage", lambda *a, **k: captured.update(k))
    r = client.post("/api/generate", json={"type": "aydinlatma"}, headers={"X-Anthropic-Key": "sk-byok"})
    assert r.status_code == 200
    assert captured["byok"] is True
