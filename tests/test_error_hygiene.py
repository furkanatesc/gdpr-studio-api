"""İstemciye giden hata yanıtları ham istisna metni sızdırmamalı (B1)."""
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

import app.config as config_module
import app.modules.generation as genmod
from app.db import get_session
from app.main import app


def test_readyz_does_not_leak_exception_text():
    def _raising_session():
        class _S:
            def execute(self, *_a, **_k):
                raise OperationalError("SELECT 1", {}, Exception("host=secret-db password=hunter2"))
        yield _S()

    app.dependency_overrides[get_session] = _raising_session
    try:
        client = TestClient(app, raise_server_exceptions=False)
        r = client.get("/readyz")
        assert r.status_code == 503
        detail = r.json()["detail"]
        assert detail == "db not ready"
        assert "secret-db" not in detail and "hunter2" not in detail
    finally:
        app.dependency_overrides.pop(get_session, None)


def _managed_billing_settings():
    config_module._settings = config_module.Settings(
        _env_file=None,
        managed_anthropic_api_key="sk-managed-test",
        allowed_origins="http://localhost:3000",
        redis_url="",
        stripe_secret_key="sk_test_x",
        stripe_webhook_secret="whsec_x",
    )


def test_generation_stream_error_event_does_not_leak_exception_text(client, monkeypatch):
    """SSE error olayı gövdesi generic mesaj taşımalı; istisna metnini içermemeli (B1)."""
    _managed_billing_settings()

    def _boom_stream(*a, **k):
        yield "grounding", []
        raise RuntimeError("host=secret-db password=hunter2")

    monkeypatch.setattr(genmod, "generate_document_stream", _boom_stream)
    monkeypatch.setattr(genmod, "capture_exception", lambda e: None)

    with client.stream("POST", "/api/generate/stream", json={"type": "aydinlatma"}) as r:
        assert r.status_code == 200
        body = "".join(r.iter_text())

    assert "event: error" in body
    assert "secret-db" not in body and "hunter2" not in body
    assert genmod.GENERIC_GENERATION_ERROR in body
