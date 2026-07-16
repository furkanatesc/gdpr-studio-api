"""Backend güvenlik başlıkları — H1-6 (mimari review).

API yanıtları JSON olsa da tarayıcı doğrudan erişebildiği (ör. paylaşılan link, hata sayfası)
ve derinlik savunması için temel güvenlik başlıkları her yanıta eklenmeli: nosniff, çerçeve
reddi, dar CSP, Referrer-Policy. HSTS yalnız prod'da (dev http'de zarar vermesin).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

import app.config as config_module
from app.main import app


def _client_with_env(environment: str) -> TestClient:
    config_module._settings = config_module.Settings(
        _env_file=None,
        managed_anthropic_api_key="",
        allowed_origins="http://localhost:3000",
        redis_url="",
        environment=environment,
    )
    return TestClient(app)


def test_security_headers_present_on_all_responses():
    with _client_with_env("development") as c:
        r = c.get("/")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in r.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]


def test_hsts_only_in_production():
    with _client_with_env("development") as c:
        dev = c.get("/")
    assert "Strict-Transport-Security" not in dev.headers

    with _client_with_env("production") as c:
        prod = c.get("/")
    assert "max-age=" in prod.headers.get("Strict-Transport-Security", "")
