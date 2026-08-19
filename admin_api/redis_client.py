"""admin-api Redis: fail-open connect (unconfigured = disabled) + rate-limit primitives.

Separate from `app/redis_client.py` (tenant service) — admin-api has its own settings and
its own degrade semantics (spec §4.3): an EMPTY `admin_redis_url` disables the limiter
entirely (dev/test); a CONFIGURED-but-unreachable Redis is a distinct "down" state that
`admin_api.middleware` degrades per request-class (fail-closed writes, local-fallback
reads) instead of the tenant service's blanket fail-open.
"""

from __future__ import annotations

import threading
import time

import redis

from .config import get_admin_settings

_client: redis.Redis | None = None
_initialized = False

_local_lock = threading.Lock()
_local_counters: dict[tuple[str, int], int] = {}


def get_admin_redis() -> redis.Redis | None:
    """Lazy singleton. Empty `admin_redis_url` -> None (disabled). Connect failure -> None
    (caller distinguishes "disabled" from "down" via `admin_redis_url` truthiness itself)."""
    global _client, _initialized
    if _initialized:
        return _client
    _initialized = True
    url = get_admin_settings().admin_redis_url
    if not url:
        _client = None
        return None
    try:
        client = redis.Redis.from_url(
            url, socket_connect_timeout=0.5, socket_timeout=0.5, decode_responses=True
        )
        client.ping()
        _client = client
    except Exception:
        _client = None
    return _client


def reset_admin_redis() -> None:
    """Test izolasyonu: singleton'ı sıfırla (ayar değişince yeniden değerlendirilsin)."""
    global _client, _initialized
    _client = None
    _initialized = False


def redis_fixed_window_allow(client: redis.Redis, key: str, limit: int, window_s: int = 60) -> bool:
    """Sabit pencere sayacı. Redis hatası burada YUTULMAZ — çağıran (middleware) sınıf-bazlı
    degrade uygulasın diye `RedisError` yükselir."""
    count = client.incr(key)
    if count == 1:
        client.expire(key, window_s)
    return int(count) <= limit


def local_fixed_window_allow(key: str, limit: int, window_s: int = 60) -> bool:
    """Redis çöktüğünde SADECE okuma yolu için süreç-içi yedek limiter (tek-instance koruma)."""
    bucket = int(time.time() // window_s)
    cache_key = (key, bucket)
    with _local_lock:
        count = _local_counters.get(cache_key, 0) + 1
        _local_counters[cache_key] = count
    return count <= limit


def reset_local_limiter() -> None:
    with _local_lock:
        _local_counters.clear()
