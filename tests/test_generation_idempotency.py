"""Idempotency-Key: ağ retry'ında çift üretim/çift fatura önlenir — H1-3 (review P1).

Kaçak: istemci timeout'ta `POST /generate`i tekrarlarsa ikinci model çağrısı yapılır →
çift doküman, çift kota, çift maliyet. Opsiyonel `Idempotency-Key` başlığı ile (org, key)
üzerinde kısa-TTL kilit tutulur; kilit duruyorken ikinci istek 409 döner.

Belge içeriği saklanmadığı için (veri minimizasyonu) yanıt tekrar oynatılmaz — kilit
yalnızca çift üretimi/faturayı engeller. Redis yoksa fail-open (özellik opsiyonel).
"""

from __future__ import annotations

import app.config as config_module
import app.idempotency as idem
import app.modules.generation as genmod
import app.redis_client as rc
from app.models import GeneratedDocument
from legal_core.models import GenerateResponse, Usage


class FakeRedis:
    """set(nx, ex) + delete destekleyen minimum sahte Redis (TTL simüle edilmez)."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    def set(self, key: str, value: str, nx: bool = False, ex: int | None = None):
        if nx and key in self.store:
            return None  # redis-py: NX başarısız → None
        self.store[key] = value
        return True

    def delete(self, key: str) -> int:
        return 1 if self.store.pop(key, None) is not None else 0

    def ping(self) -> bool:
        return True


def _managed_billing_settings():
    config_module._settings = config_module.Settings(
        _env_file=None,
        managed_anthropic_api_key="sk-managed-test",
        allowed_origins="http://localhost:3000",
        redis_url="",  # get_redis monkeypatch'lenir; rate-limit fail-open kalır
        stripe_secret_key="sk_test_x",
        stripe_webhook_secret="whsec_x",
    )


def _use_fake_redis(monkeypatch) -> FakeRedis:
    fake = FakeRedis()
    monkeypatch.setattr(idem, "get_redis", lambda: fake)
    monkeypatch.setattr(rc, "get_redis", lambda: fake)
    return fake


def _fake_response():
    return GenerateResponse(
        text="metin", grounding=[], model="claude-sonnet-4-6",
        disclaimer="d", usage=Usage(input_tokens=100, output_tokens=200),
    )


def _post(client, key: str | None = None):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post("/api/generate", json={"type": "aydinlatma"}, headers=headers)


def test_duplicate_key_rejected_without_second_generation(client, db_session, monkeypatch):
    """Aynı anahtarla ikinci istek → 409; model ikinci kez ÇAĞRILMAZ, ikinci kez sayılmaz."""
    _managed_billing_settings()
    _use_fake_redis(monkeypatch)
    calls = {"n": 0}

    def _counted(*a, **k):
        calls["n"] += 1
        return _fake_response()

    monkeypatch.setattr(genmod, "generate_document", _counted)

    assert _post(client, "abc-123").status_code == 200
    dup = _post(client, "abc-123")

    assert dup.status_code == 409
    assert dup.json()["detail"]["code"] == "duplicate_request"
    assert calls["n"] == 1  # çift model çağrısı yok
    assert db_session.query(GeneratedDocument).count() == 1  # çift kota/doküman yok


def test_different_keys_both_generate(client, monkeypatch):
    _managed_billing_settings()
    _use_fake_redis(monkeypatch)
    monkeypatch.setattr(genmod, "generate_document", lambda *a, **k: _fake_response())

    assert _post(client, "key-1").status_code == 200
    assert _post(client, "key-2").status_code == 200


def test_without_key_no_lock(client, monkeypatch):
    """Başlık opsiyonel: gönderilmezse davranış değişmez (kilit yok)."""
    _managed_billing_settings()
    _use_fake_redis(monkeypatch)
    monkeypatch.setattr(genmod, "generate_document", lambda *a, **k: _fake_response())

    assert _post(client).status_code == 200
    assert _post(client).status_code == 200


def test_failed_generation_releases_key(client, monkeypatch):
    """Üretim patlarsa kilit bırakılır → istemci AYNI anahtarla yeniden deneyebilir."""
    _managed_billing_settings()
    _use_fake_redis(monkeypatch)

    def _boom(*a, **k):
        raise RuntimeError("model patladı")

    monkeypatch.setattr(genmod, "generate_document", _boom)
    assert _post(client, "retry-me").status_code == 502

    monkeypatch.setattr(genmod, "generate_document", lambda *a, **k: _fake_response())
    assert _post(client, "retry-me").status_code == 200  # kilit bırakıldı


def test_stream_duplicate_key_rejected(client, monkeypatch):
    """Web asıl akış ucunu kullanır → kilit orada da geçerli olmalı."""
    _managed_billing_settings()
    _use_fake_redis(monkeypatch)

    def _fake_stream(*a, **k):
        yield "grounding", []
        yield "delta", "me"
        yield "done", {"model": "claude-sonnet-4-6", "usage": {"inputTokens": 10, "outputTokens": 20}}

    monkeypatch.setattr(genmod, "generate_document_stream", _fake_stream)
    headers = {"Idempotency-Key": "stream-1"}
    with client.stream("POST", "/api/generate/stream", json={"type": "cerez"}, headers=headers) as r:
        assert r.status_code == 200
        "".join(r.iter_text())

    dup = client.post("/api/generate/stream", json={"type": "cerez"}, headers=headers)
    assert dup.status_code == 409


def test_too_long_key_rejected(client, monkeypatch):
    _managed_billing_settings()
    _use_fake_redis(monkeypatch)
    monkeypatch.setattr(genmod, "generate_document", lambda *a, **k: _fake_response())

    r = _post(client, "x" * (idem.MAX_KEY_LENGTH + 1))
    assert r.status_code == 400


def test_redis_disabled_fails_open(client, monkeypatch):
    """Redis yoksa özellik sessizce devre dışı — üretim engellenmez."""
    _managed_billing_settings()
    monkeypatch.setattr(idem, "get_redis", lambda: None)
    monkeypatch.setattr(genmod, "generate_document", lambda *a, **k: _fake_response())

    assert _post(client, "same").status_code == 200
    assert _post(client, "same").status_code == 200
