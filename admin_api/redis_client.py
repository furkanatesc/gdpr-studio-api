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
_last_attempt: float = 0.0
_RETRY_COOLDOWN_S = 5.0

_conn_lock = threading.Lock()
_local_lock = threading.Lock()
_local_counters: dict[tuple[str, int], int] = {}


def get_admin_redis() -> redis.Redis | None:
    """Cooldown'lu yeniden-deneme singleton. Bağlanan client süresiz cache'lenir. Client yokken
    en fazla `_RETRY_COOLDOWN_S` saniyede bir yeniden bağlantı denenir — bir Redis blip'i
    sürecin ömrü boyunca kalıcı `None` haline GELMEZ (bkz. review C1). Boş `admin_redis_url`
    -> None (disabled, caller `admin_redis_url` truthiness'ından ayırt eder).

    `_conn_lock`: bağlantı+global-mutasyonu serileştirir (çağıran `asyncio.to_thread` ile ayrı
    worker thread'lerden gelir). Kilit içinde tekrar-kontrol → başarısız bir thread'in `_client=None`
    yazması, eşzamanlı başarılı bir bağlantıyı EZEMEZ (re-review #3)."""
    global _client, _last_attempt
    if _client is not None:
        return _client
    url = get_admin_settings().admin_redis_url
    if not url:
        return None
    with _conn_lock:
        if _client is not None:  # başka thread bu arada bağlandı
            return _client
        now = time.monotonic()
        if now - _last_attempt < _RETRY_COOLDOWN_S:
            return None
        _last_attempt = now
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
    global _client, _last_attempt
    _client = None
    _last_attempt = 0.0


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
