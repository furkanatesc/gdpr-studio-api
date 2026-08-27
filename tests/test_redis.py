"""Redis: rate-limit + cache yardımcıları (fake istemci ile, gerçek Redis gerektirmez)."""

from __future__ import annotations

import time

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


def test_get_redis_retries_after_transient_failure(monkeypatch):
    """Geçici bir Redis blip'i, Redis'i sürecin ömrü boyunca kalıcı DEVRE DIŞI bırakmamalı:
    cooldown sonrası yeniden bağlanıp iyileşmeli (sticky-singleton regresyonunu yakalar)."""
    rc.reset_redis()
    monkeypatch.setattr(cfg._settings, "redis_url", "redis://unused:6379/0")

    clock = {"t": 1000.0}
    monkeypatch.setattr(time, "monotonic", lambda: clock["t"])

    calls = {"n": 0}
    good = FakeRedis()

    class Boom:
        def ping(self):
            raise RuntimeError("transient down")

    def fake_from_url(url, **kwargs):
        calls["n"] += 1
        return Boom() if calls["n"] == 1 else good

    monkeypatch.setattr(rc.redis.Redis, "from_url", staticmethod(fake_from_url))

    assert rc.get_redis() is None  # ilk deneme: bağlanamadı
    assert rc.get_redis() is None  # cooldown içinde: yeniden DENEME yok
    assert calls["n"] == 1

    clock["t"] += 10.0  # cooldown geçti
    assert rc.get_redis() is good  # yeniden dener + iyileşir
    assert calls["n"] == 2

    rc.reset_redis()


def test_get_redis_unconfigured_stays_none(monkeypatch):
    """Boş redis_url → None, ve from_url'e hiç dokunmadan (bağlantı fırtınası yok)."""
    rc.reset_redis()
    monkeypatch.setattr(cfg._settings, "redis_url", "")

    def boom_from_url(*a, **k):
        raise AssertionError("boş url ile bağlanmaya çalışılmamalı")

    monkeypatch.setattr(rc.redis.Redis, "from_url", staticmethod(boom_from_url))
    assert rc.get_redis() is None
    assert rc.get_redis() is None
    rc.reset_redis()


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
