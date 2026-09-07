"""classify_generation_error — Anthropic istisnasını spesifik, PII-güvenli Türkçe
mesaja eşler (B-ticket: kredi/rate-limit/auth/overload farklı görünsün, geri kalanı
GENERIC_GENERATION_ERROR'a düşsün). Ham istisna mesajı asla döndürülmemeli — yalnız
sabit şablonlar; kredi durumunda dahi eşleşme dar bir alt-dizge kontrolüyle, exception
TÜRÜNE göre yapılır.
"""

from __future__ import annotations

import httpx
from anthropic import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    OverloadedError,
    RateLimitError,
)

from app.modules.generation import (
    AUTH_ERROR,
    CREDIT_BALANCE_ERROR,
    GENERIC_GENERATION_ERROR,
    RATE_LIMIT_ERROR,
    SERVICE_UNAVAILABLE_ERROR,
    classify_generation_error,
)

_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_error(cls, message: str, status_code: int):
    response = httpx.Response(status_code=status_code, request=_REQUEST, text=message)
    body = {"error": {"type": "error", "message": message}}
    return cls(message, response=response, body=body)


def test_credit_balance_bad_request_maps_to_credit_message():
    exc = _status_error(
        BadRequestError,
        "Your credit balance is too low to access the Anthropic API.",
        400,
    )
    assert classify_generation_error(exc) == CREDIT_BALANCE_ERROR


def test_other_bad_request_maps_to_generic():
    # 400 ama kredi ile ilgisiz (ör. istek şeması hatası) -> generic'e düşsün,
    # ham mesaj asla dışarı sızmasın.
    exc = _status_error(BadRequestError, "max_tokens: field required", 400)
    assert classify_generation_error(exc) == GENERIC_GENERATION_ERROR


def test_rate_limit_error_maps_to_rate_message():
    exc = _status_error(RateLimitError, "Rate limit reached for requests", 429)
    assert classify_generation_error(exc) == RATE_LIMIT_ERROR


def test_authentication_error_maps_to_auth_message():
    exc = _status_error(AuthenticationError, "invalid x-api-key", 401)
    assert classify_generation_error(exc) == AUTH_ERROR


def test_overloaded_error_maps_to_service_unavailable_message():
    exc = _status_error(OverloadedError, "Overloaded", 529)
    assert classify_generation_error(exc) == SERVICE_UNAVAILABLE_ERROR


def test_internal_server_error_maps_to_service_unavailable_message():
    exc = _status_error(InternalServerError, "Internal server error", 500)
    assert classify_generation_error(exc) == SERVICE_UNAVAILABLE_ERROR


def test_connection_error_maps_to_service_unavailable_message():
    exc = APIConnectionError(request=_REQUEST)
    assert classify_generation_error(exc) == SERVICE_UNAVAILABLE_ERROR


def test_unknown_exception_maps_to_generic_fallback():
    assert classify_generation_error(ValueError("beklenmedik hata")) == GENERIC_GENERATION_ERROR


def test_returned_message_never_echoes_raw_exception_text():
    # PII sızıntısı guard'ı: dönen mesaj sabit şablonlardan biri olmalı, istisnanın
    # kendi mesaj metnini (prompt/PII taşıyabilir) hiçbir şekilde içermemeli.
    secret = "musteri-pii-icerikli-detay-12345"
    exc = _status_error(BadRequestError, f"schema error: {secret}", 400)
    result = classify_generation_error(exc)
    assert secret not in result
    assert result == GENERIC_GENERATION_ERROR
