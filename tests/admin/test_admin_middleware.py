"""AdminRateLimitMiddleware — trusted-hop IP (never XFF) + degrade rate-limit (spec §4.3).

Tests wrap the middleware directly around a minimal echo ASGI app (not the full FastAPI
`app`) so degrade semantics can be exercised without auth/db wiring — the middleware runs
before routing, so its behavior is independent of what's behind it. A separate smoke test
confirms it is actually registered on the real `admin_api.main.app`.
"""

from __future__ import annotations

import json
import logging

import pytest
from fastapi.testclient import TestClient
from redis.exceptions import RedisError

import admin_api.middleware as middleware_module
import admin_api.redis_client as redis_client_module
from admin_api.config import AdminSettings
from admin_api.main import app as real_app
from admin_api.middleware import AdminRateLimitMiddleware
from admin_api.redis_client import get_admin_redis, reset_admin_redis, reset_local_limiter
from admin_api.request_context import get_admin_client_ip


async def _echo_app(scope, receive, send):
    ip = get_admin_client_ip()
    body = json.dumps({"ip": ip}).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"content-type", b"application/json")],
        }
    )
    await send({"type": "http.response.body", "body": body})


@pytest.fixture(autouse=True)
def _isolate():
    reset_admin_redis()
    reset_local_limiter()
    yield
    reset_admin_redis()
    reset_local_limiter()


def _client(monkeypatch, settings: AdminSettings) -> TestClient:
    monkeypatch.setattr(middleware_module, "get_admin_settings", lambda: settings)
    return TestClient(AdminRateLimitMiddleware(_echo_app))


class _ErroringRedis:
    def incr(self, key):
        raise RedisError("down")


class _FakeRedis:
    def __init__(self):
        self._counts: dict[str, int] = {}

    def incr(self, key):
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    def expire(self, key, ttl):
        pass


def test_get_admin_redis_retries_after_cooldown(monkeypatch):
    settings = AdminSettings(admin_redis_url="redis://down")
    monkeypatch.setattr(redis_client_module, "get_admin_settings", lambda: settings)

    calls = {"n": 0}

    class _FakePingClient:
        def ping(self):
            return True

    def _from_url(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("blip")
        return _FakePingClient()

    monkeypatch.setattr(redis_client_module.redis.Redis, "from_url", _from_url)

    assert get_admin_redis() is None
    assert calls["n"] == 1

    monkeypatch.setattr(
        redis_client_module.time,
        "monotonic",
        lambda: redis_client_module._last_attempt + 10.0,
    )
    client = get_admin_redis()
    assert isinstance(client, _FakePingClient)
    assert calls["n"] == 2


def test_get_admin_redis_does_not_retry_within_cooldown(monkeypatch):
    settings = AdminSettings(admin_redis_url="redis://down")
    monkeypatch.setattr(redis_client_module, "get_admin_settings", lambda: settings)

    calls = {"n": 0}

    def _from_url(*args, **kwargs):
        calls["n"] += 1
        raise ConnectionError("still down")

    monkeypatch.setattr(redis_client_module.redis.Redis, "from_url", _from_url)

    assert get_admin_redis() is None
    assert calls["n"] == 1

    assert get_admin_redis() is None
    assert calls["n"] == 1


def test_middleware_registered_on_app():
    assert any(
        getattr(m, "cls", None) is AdminRateLimitMiddleware for m in real_app.user_middleware
    )


def test_xff_never_trusted(monkeypatch):
    client = _client(monkeypatch, AdminSettings(admin_redis_url=""))
    resp = client.get("/admin/audit", headers={"X-Forwarded-For": "1.2.3.4"})
    assert resp.status_code == 200
    assert resp.json()["ip"] != "1.2.3.4"


def test_unconfigured_disables_limiter(monkeypatch):
    client = _client(
        monkeypatch, AdminSettings(admin_redis_url="", admin_rate_limit_read_per_min=1)
    )
    for _ in range(10):
        assert client.get("/admin/audit").status_code == 200


def test_configured_down_read_degrades_then_429(monkeypatch, caplog):
    settings = AdminSettings(admin_redis_url="redis://down", admin_rate_limit_read_per_min=2)
    monkeypatch.setattr(middleware_module, "get_admin_settings", lambda: settings)
    monkeypatch.setattr(middleware_module, "get_admin_redis", lambda: _ErroringRedis())
    client = TestClient(AdminRateLimitMiddleware(_echo_app))

    with caplog.at_level(logging.WARNING, logger="admin_api.ratelimit"):
        r1 = client.get("/admin/audit")
        r2 = client.get("/admin/audit")
        r3 = client.get("/admin/audit")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert r3.headers.get("retry-after") == "60"
    assert any("degraded to local rate-limit fallback" in rec.message for rec in caplog.records)


def test_configured_down_write_fails_closed(monkeypatch, caplog):
    settings = AdminSettings(admin_redis_url="redis://down")
    monkeypatch.setattr(middleware_module, "get_admin_settings", lambda: settings)
    monkeypatch.setattr(middleware_module, "get_admin_redis", lambda: _ErroringRedis())
    client = TestClient(AdminRateLimitMiddleware(_echo_app))

    with caplog.at_level(logging.ERROR, logger="admin_api.ratelimit"):
        resp = client.post("/admin/impersonation", json={})

    assert resp.status_code == 503
    assert resp.json()["detail"] == "rate_limiter_unavailable"
    assert any("failing closed" in rec.message for rec in caplog.records)


def _set_admin_bff_secret(monkeypatch, secret: str) -> AdminSettings:
    settings = AdminSettings(admin_redis_url="", admin_bff_secret=secret)
    monkeypatch.setattr(middleware_module, "get_admin_settings", lambda: settings)
    return settings


def _client_with_middleware(capture_client_ip_into: dict | None = None) -> TestClient:
    async def _app(scope, receive, send):
        if capture_client_ip_into is not None:
            capture_client_ip_into["client_ip"] = get_admin_client_ip()
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": b"{}"})

    return TestClient(AdminRateLimitMiddleware(_app))


def test_missing_bff_secret_rejected_when_configured(monkeypatch):
    _set_admin_bff_secret(monkeypatch, "s3cret")
    client = _client_with_middleware()
    r = client.get("/admin/healthz")  # no X-Admin-BFF-Secret
    assert r.status_code == 403


def test_matching_bff_secret_allows_and_uses_forwarded_ip(monkeypatch):
    _set_admin_bff_secret(monkeypatch, "s3cret")
    seen: dict = {}
    client = _client_with_middleware(capture_client_ip_into=seen)
    r = client.get(
        "/admin/healthz",
        headers={"X-Admin-BFF-Secret": "s3cret", "X-Admin-Client-IP": "203.0.113.7"},
    )
    assert r.status_code == 200
    assert seen["client_ip"] == "203.0.113.7"


def test_empty_secret_no_enforcement(monkeypatch):
    _set_admin_bff_secret(monkeypatch, "")
    client = _client_with_middleware()
    assert client.get("/admin/healthz").status_code == 200


def test_configured_up_rate_limits_over_threshold(monkeypatch):
    settings = AdminSettings(admin_redis_url="redis://up", admin_rate_limit_read_per_min=2)
    fake = _FakeRedis()
    monkeypatch.setattr(middleware_module, "get_admin_settings", lambda: settings)
    monkeypatch.setattr(middleware_module, "get_admin_redis", lambda: fake)
    client = TestClient(AdminRateLimitMiddleware(_echo_app))

    r1 = client.get("/admin/audit")
    r2 = client.get("/admin/audit")
    r3 = client.get("/admin/audit")

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r3.status_code == 429
    assert r3.headers.get("retry-after") == "60"
