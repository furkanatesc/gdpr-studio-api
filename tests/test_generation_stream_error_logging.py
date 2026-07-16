"""Streaming üretim hatası ops'a görünür olmalı — H1-5 (mimari review güvenilirlik).

Sorun: akış `except` dalı yalnız SSE error olayı yayınlıyordu; `_log.exception`/Sentry YOK.
Yanıt 200 başladıktan sonra patladığı için erişim middleware'i de 200 kaydeder → en pahalı
işlem (model üretimi) hatası izlemede tamamen kör kalır. Bu test: stream sağlayıcısı
patladığında (a) SSE error olayı yine çıkar, (b) ERROR log + Sentry capture tetiklenir.
"""

from __future__ import annotations

import logging

import app.config as config_module
import app.modules.generation as genmod


def _managed_billing_settings():
    config_module._settings = config_module.Settings(
        _env_file=None,
        managed_anthropic_api_key="sk-managed-test",
        allowed_origins="http://localhost:3000",
        redis_url="",
        stripe_secret_key="sk_test_x",
        stripe_webhook_secret="whsec_x",
    )


def test_stream_error_is_logged_and_captured(client, monkeypatch, caplog):
    _managed_billing_settings()

    def _boom_stream(*a, **k):
        yield "grounding", []
        raise RuntimeError("model akışı patladı")

    monkeypatch.setattr(genmod, "generate_document_stream", _boom_stream)

    captured: list[BaseException] = []
    monkeypatch.setattr(genmod, "capture_exception", lambda e: captured.append(e))

    with caplog.at_level(logging.ERROR, logger="app.generation"):
        with client.stream("POST", "/api/generate/stream", json={"type": "aydinlatma"}) as r:
            assert r.status_code == 200  # akış zaten başladı → status 200
            body = "".join(r.iter_text())

    # (a) istemci yine bir hata olayı görür
    assert "event: error" in body
    # (b) ops görünürlüğü: ERROR log + Sentry capture
    errors = [rec for rec in caplog.records if rec.levelno >= logging.ERROR]
    assert any("üretim" in rec.getMessage().lower() or "stream" in rec.getMessage().lower()
               for rec in errors), f"beklenen ERROR log yok: {[r.getMessage() for r in errors]}"
    assert len(captured) == 1
    assert isinstance(captured[0], RuntimeError)
