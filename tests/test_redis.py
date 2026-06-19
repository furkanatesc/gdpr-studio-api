"""Redis: rate-limit + cache yardımcıları (fake istemci ile, gerçek Redis gerektirmez)."""

from __future__ import annotations

import app.config as cfg
import app.redis_client as rc
from app.redis_client import _allow, cache_get_json, cache_set_json


class FakeRedis:
    """Testler için minimum sahte Redis — incr/expire/get/set/ping."""

    def __init__(self) -> None:
        self.store: dict[str, object] = {}

    def incr(self, key: str) -> int:
        self.store[key] = int(self.store.get(key, 0)) + 1  # type: ignore[arg-type]
        return self.store[key]  # type: ignore[return-value]

    def expire(self, key: str, ttl: int) -> bool:
        return True

    def get(self, key: str):
        return self.store.get(key)

    def set(self, key: str, value, ex=None) -> None:
        self.store[key] = value

    def ping(self) -> bool:
        return True


def test_allow_limit_asilinca_engeller():
    r = FakeRedis()
    assert all(_allow(r, "k", 3) for _ in range(3))  # ilk 3 geçer
    assert not _allow(r, "k", 3)  # 4. limit aşımı


def test_allow_fail_open_redis_hatasinda():
    class Boom:
        def incr(self, key):
            raise RuntimeError("redis down")

    assert _allow(Boom(), "k", 1) is True  # hata → izin ver (fail-open)


def test_cache_json_roundtrip(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(rc, "get_redis", lambda: fake)
    assert cache_get_json("x") is None  # boş
    cache_set_json("x", ["a", "b"], 10)
    assert cache_get_json("x") == ["a", "b"]


def test_generate_rate_limit_429(client, monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(rc, "get_redis", lambda: fake)
    monkeypatch.setattr(cfg._settings, "rate_limit_generate_per_min", 3)

    body = {"type": "aydinlatma", "fields": {}, "veriler": []}
    codes = [client.post("/api/generate", json=body).status_code for _ in range(4)]

    # İlk 3 rate-limit'i geçer → anahtarsız 400; 4. istek limiti aşar → 429.
    assert codes[:3] == [400, 400, 400]
    assert codes[3] == 429
