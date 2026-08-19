"""Trusted-hop admin client IP — set by `AdminRateLimitMiddleware` from the ASGI socket
peer ONLY (never `X-Forwarded-For`). Separate module (not middleware.py) so `audit.py`
can import the getter without importing middleware.py (avoids an import cycle).
"""

from __future__ import annotations

from contextvars import ContextVar, Token

_admin_client_ip: ContextVar[str | None] = ContextVar("_admin_client_ip", default=None)


def set_admin_client_ip(ip: str | None) -> Token:
    return _admin_client_ip.set(ip)


def get_admin_client_ip() -> str | None:
    return _admin_client_ip.get()


def reset_admin_client_ip(token: Token) -> None:
    _admin_client_ip.reset(token)
