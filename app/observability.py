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
    """DSN varsa Sentry'yi başlatır.

    KVKK: send_default_pii=False (PII/başlık/çerez gönderilmez) TEK BAŞINA frame local'lerini
    kapatmaz — include_local_variables sentry-sdk'de varsayılan True'dur ve capture_exception
    hatanın stack frame'lerindeki yerel değişkenleri (ör. müvekkil envanteri, üretilmiş belge
    metni) serileştirip gönderirdi. include_local_variables=False bunu kapatır.
    """
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=0.0,  # performans tracing Faz 4 (OTel ile); şimdilik yalnız hata.
        send_default_pii=False,
        include_local_variables=False,
    )
    return True


class SecurityHeadersMiddleware:
    """Her yanıta temel güvenlik başlıkları ekler (pure-ASGI, SSE'yi bozmaz).

    API JSON döndürse de tarayıcı doğrudan erişebildiği için derinlik savunması: nosniff,
    çerçeve reddi, dar CSP (API içerik sunmaz → default-src 'none'), Referrer-Policy.
    HSTS yalnız prod'da (dev http bağlantısını kırmasın). CORS başlıklarına dokunmaz.
    """

    _STATIC = (
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"no-referrer"),
        (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'; base-uri 'none'"),
    )
    _HSTS = (b"strict-transport-security", b"max-age=63072000; includeSubDomains")

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # HSTS kararı istek anında ayardan: dev http'de kapalı, prod https'te açık.
        from .config import get_settings

        headers_to_add = list(self._STATIC)
        if get_settings().environment == "production":
            headers_to_add.append(self._HSTS)

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                existing = {k.lower() for k, _ in headers}
                for key, value in headers_to_add:
                    if key not in existing:  # el ile set edilmişse ezme
                        headers.append((key, value))
            await send(message)

        await self.app(scope, receive, send_wrapper)


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
