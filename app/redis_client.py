"""Redis: bağlantı (env-gated, graceful) + rate-limit + cache yardımcıları.

Tasarım ilkesi: Redis OPSİYONELDİR. `REDIS_URL` boşsa ya da Redis erişilemezse
uygulama çalışmaya devam eder — rate-limit **fail-open** (isteğe izin verir), cache
**miss** döner. Böylece altyapı kısmi arızada üretim durmaz (NFR: erişilebilirlik).

Endpoint'ler sync olduğundan sync `redis.Redis` istemcisi kullanılır.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any

import redis
from fastapi import Depends, HTTPException, Request

from .config import get_settings
from .modules.auth import Tenant, get_current_tenant

_log = logging.getLogger("app.redis")

_client: redis.Redis | None = None
_last_attempt: float = 0.0
_RETRY_COOLDOWN_S = 5.0
_conn_lock = threading.Lock()


def get_redis() -> redis.Redis | None:
    """Cooldown'lu yeniden-deneme singleton; yapılandırılmamış/erişilemezse None (özellik devre dışı).

    Bağlanan client süresiz cache'lenir. Client yokken en fazla `_RETRY_COOLDOWN_S` saniyede bir
    yeniden bağlanmayı dener → geçici bir Redis blip'i sürecin ömrü boyunca KALICI `None` haline
    GELMEZ; Redis dönünce rate-limit/idempotency koruması otomatik geri gelir. Boş `redis_url` → None.

    `_conn_lock` bağlantı+global-mutasyonu serileştirir (sync uçlar Starlette threadpool'undan
    eşzamanlı gelir); kilit içinde tekrar-kontrol, başarısız bir thread'in eşzamanlı başarılı
    bağlantıyı ezmesini önler.
    """
    global _client, _last_attempt
    if _client is not None:
        return _client
    url = get_settings().redis_url
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
        except Exception as e:  # bağlanılamadı → sessizce devre dışı (cooldown sonrası tekrar denenir)
            _log.warning("Redis erişilemedi, devre dışı: %s", e)
            _client = None
        return _client


def reset_redis() -> None:
    """Test izolasyonu: singleton'ı sıfırla (ayar değişince yeniden değerlendirilsin)."""
    global _client, _last_attempt
    _client = None
    _last_attempt = 0.0


# --- Rate limit (sabit pencere sayacı) ---------------------------------------

def _allow(client: redis.Redis, key: str, limit: int, window_s: int = 60) -> bool:
    """Pencere içinde `key` için sayaç limit'i aşmıyorsa True. Hata → fail-open (True)."""
    try:
        count = client.incr(key)
        if count == 1:
            client.expire(key, window_s)
        return int(count) <= limit
    except Exception as e:  # Redis op hatası → engelleme, izin ver
        _log.warning("Rate-limit Redis hatası (fail-open): %s", e)
        return True


def generate_rate_limit(
    request: Request,
    tenant: Tenant = Depends(get_current_tenant),
) -> None:
    """Üretim uçları için tenant başına dakikalık rate-limit (Redis yoksa fail-open)."""
    client = get_redis()
    if client is None:
        return
    limit = get_settings().rate_limit_generate_per_min
    if not _allow(client, f"rl:generate:{tenant.id}", limit):
        raise HTTPException(
            status_code=429,
            detail="Çok fazla üretim isteği. Lütfen biraz bekleyip tekrar deneyin.",
        )


# --- Cache (JSON) ------------------------------------------------------------

def cache_get_json(key: str) -> Any | None:
    client = get_redis()
    if client is None:
        return None
    try:
        raw = client.get(key)
        return json.loads(raw) if raw is not None else None
    except Exception as e:
        _log.warning("Cache get hatası (miss): %s", e)
        return None


def cache_set_json(key: str, value: Any, ttl_s: int) -> None:
    client = get_redis()
    if client is None:
        return
    try:
        client.set(key, json.dumps(value, ensure_ascii=False), ex=ttl_s)
    except Exception as e:
        _log.warning("Cache set hatası (yoksayıldı): %s", e)
