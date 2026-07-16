"""Gözlemlenebilirlik: yapısal (JSON) loglama + Sentry (env-gated) + istek bağlamı.

- `configure_logging`: kök logger'ı stdout'a JSON yazan tek handler'a bağlar.
- `init_sentry`: yalnızca SENTRY_DSN tanımlıysa Sentry'yi başlatır (KVKK: PII gönderilmez).
- `RequestContextMiddleware`: **pure-ASGI** (BaseHTTPMiddleware DEĞİL — o, gövdeyi
  buffer'layıp SSE streaming'i bozar). Her isteğe request_id atar, `X-Request-ID` döndürür,
  yapısal erişim logu yazar.
"""

from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar

from starlette.types import ASGIApp, Receive, Scope, Send

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


def capture_exception(exc: BaseException) -> None:
    """Hatayı Sentry'ye gönder (kuruluysa). DSN yoksa sessizce no-op.

    Streaming üretim gibi yanıt 200 başladıktan SONRA patlayan işlemler erişim
    middleware'ine görünmez; onları ops'a taşımak için buradan capture edilir.
    """
    try:
        import sentry_sdk

        sentry_sdk.capture_exception(exc)  # init edilmemişse SDK içinde no-op
    except Exception:  # gözlemlenebilirlik asla asıl akışı bozmamalı
        pass


class JsonFormatter(logging.Formatter):
    """Log kaydını tek satır JSON'a çevirir; varsa request_id ve ekstra alanları katar."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        rid = _request_id.get()
        if rid:
            payload["request_id"] = rid
        for key, val in getattr(record, "extra_fields", {}).items():
            payload[key] = val
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # uvicorn erişim logu çift kayıt yapmasın — bizim middleware'imiz yazıyor.
    logging.getLogger("uvicorn.access").handlers.clear()
    logging.getLogger("uvicorn.access").propagate = False


def init_sentry(dsn: str, environment: str) -> bool:
    """DSN varsa Sentry'yi başlatır. KVKK: send_default_pii=False (PII/başlık/çerez gönderilmez)."""
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=0.0,  # performans tracing Faz 4 (OTel ile); şimdilik yalnız hata.
        send_default_pii=False,
    )
    return True


_access_logger = logging.getLogger("app.access")


class RequestContextMiddleware:
    """request_id ata, X-Request-ID döndür, yapısal erişim logu yaz (gövdeyi buffer'lamadan)."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        rid_bytes = headers.get(b"x-request-id")
        rid = rid_bytes.decode("latin-1") if rid_bytes else uuid.uuid4().hex
        token = _request_id.set(rid)
        start = time.perf_counter()
        status = {"code": 500}

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                message.setdefault("headers", []).append((b"x-request-id", rid.encode("latin-1")))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            _access_logger.exception(
                "istek hatası",
                extra={"extra_fields": {
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "duration_ms": duration_ms,
                }},
            )
            raise
        else:
            duration_ms = round((time.perf_counter() - start) * 1000, 1)
            _access_logger.info(
                "istek",
                extra={"extra_fields": {
                    "method": scope.get("method"),
                    "path": scope.get("path"),
                    "status": status["code"],
                    "duration_ms": duration_ms,
                }},
            )
        finally:
            _request_id.reset(token)
