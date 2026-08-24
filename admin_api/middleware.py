"""Pure-ASGI trusted-hop IP stamping + degrade rate-limit middleware (spec §4.3).

NOT `BaseHTTPMiddleware` (buffers the body / breaks streaming — see `app/observability.py`).
Trusted IP = the ASGI socket peer (`scope["client"][0]`) by default — NEVER a bare
`X-Forwarded-For` (spoofable; see the `app/observability.py:162` anti-pattern this
deliberately does not copy). The one exception: when a valid `X-Admin-BFF-Secret` is
present, the request is confirmed to have come through the trusted BFF hop, so the
BFF-forwarded `X-Admin-Client-IP` header is trusted as the real client IP instead.

Degrade semantics:
- `admin_redis_url` UNCONFIGURED (empty) -> limiter fully DISABLED, pass through (IP still
  stamped). Keeps dev/test and any Redis-less deploy working.
- `admin_redis_url` CONFIGURED but Redis unreachable (a real blip) -> degrade:
  mutating (POST/PUT/PATCH/DELETE) fail-closed 503; reads fall back to an in-process local
  limiter. Both alarm-log. This is distinct from "unconfigured" — see `redis_client.py`.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import logging

from redis.exceptions import RedisError

from .config import get_admin_settings
from .redis_client import get_admin_redis, local_fixed_window_allow, redis_fixed_window_allow
from .request_context import reset_admin_client_ip, resolve_admin_client_ip, set_admin_client_ip

_log = logging.getLogger("admin_api.ratelimit")

_EXEMPT_PATHS = {"/admin/healthz", "/openapi.json", "/docs", "/redoc"}
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_BFF_SECRET_HEADER = b"x-admin-bff-secret"
_BFF_CLIENT_IP_HEADER = b"x-admin-client-ip"


async def _send_json(send, status: int, detail: str, retry_after: int | None = None) -> None:
    headers = [(b"content-type", b"application/json")]
    if retry_after is not None:
        headers.append((b"retry-after", str(retry_after).encode("latin-1")))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": json.dumps({"detail": detail}).encode()})


class AdminRateLimitMiddleware:
    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        socket_ip = client[0] if client else None
        headers = dict(scope.get("headers") or [])
        path = scope.get("path", "")
        is_healthz = path == "/admin/healthz"

        settings = get_admin_settings()

        bff_secret_ok = False
        if settings.admin_bff_secret:
            provided = headers.get(_BFF_SECRET_HEADER, b"").decode("latin-1")
            bff_secret_ok = hmac.compare_digest(provided, settings.admin_bff_secret)
            # /admin/healthz is exempt from the secret gate itself (platform health
            # probes hit it directly, without the BFF hop, and must never 403) — but
            # it still benefits from IP-trust above if a valid secret happens to be
            # present, and every other admin path (incl. /openapi.json, /docs,
            # /redoc) stays gated.
            if not bff_secret_ok and not is_healthz:
                await _send_json(send, 403, "forbidden")
                return

        forwarded_ip_raw = headers.get(_BFF_CLIENT_IP_HEADER)
        forwarded_ip = forwarded_ip_raw.decode("latin-1") if forwarded_ip_raw else None
        ip = resolve_admin_client_ip(
            socket_ip=socket_ip, bff_secret_ok=bff_secret_ok, forwarded_ip=forwarded_ip
        )

        token = set_admin_client_ip(ip)
        try:
            if path in _EXEMPT_PATHS:
                await self.app(scope, receive, send)
                return

            if not settings.admin_redis_url:  # unconfigured -> limiter disabled
                await self.app(scope, receive, send)
                return

            method = scope.get("method", "GET")
            mutating = method in _MUTATING_METHODS
            limit = (
                settings.admin_rate_limit_write_per_min
                if mutating
                else settings.admin_rate_limit_read_per_min
            )
            key = f"admin_rl:{'write' if mutating else 'read'}:{ip or 'unknown'}"

            redis = await asyncio.to_thread(get_admin_redis)
            down = redis is None
            if not down:
                try:
                    allowed = await asyncio.to_thread(redis_fixed_window_allow, redis, key, limit)
                except RedisError:
                    down = True
                else:
                    if not allowed:
                        await _send_json(send, 429, "rate_limited", retry_after=60)
                        return
                    await self.app(scope, receive, send)
                    return

            # down: configured-but-unreachable (connect failure or RedisError mid-request).
            if mutating:
                _log.error("Redis down — failing closed on %s %s", method, path)
                await _send_json(send, 503, "rate_limiter_unavailable")
                return
            _log.warning("Redis down — degraded to local rate-limit fallback")
            if not local_fixed_window_allow(key, limit):
                await _send_json(send, 429, "rate_limited", retry_after=60)
                return
            await self.app(scope, receive, send)
        finally:
            reset_admin_client_ip(token)
