"""AnthropicProvider dayanıklılığı — H1-4 (mimari review P1/güvenilirlik).

Sorun: Anthropic çağrısında timeout/retry YOKKEN upstream asılırsa event loop + DB
bağlantısı ~10 dk tutulur → birkaç asılı çağrı isteği yanıtsız bırakır. Fix: client
`timeout` + `max_retries` ile kurulmalı. Bu test, lazy import edilen
`anthropic.AsyncAnthropic`'in bu kwarg'larla çağrıldığını yakalar (ağ yok — client sahte).

NOT (2026-09-09): timeout DÜZ FLOAT (saniye) olarak geçilmeli — `httpx.Timeout` nesnesi
DEĞİL. anthropic SDK'nın yeni sürümleri `httpx2` kullanıyor ve `httpx.Timeout` nesnesini
reddediyor (`TypeError: ... use httpx2.Timeout`). Float her iki SDK sürümünde de geçerli
ve SDK'nın hangi httpx'i kullandığından bağımsız — kontratı buna sabitliyoruz.
"""

from __future__ import annotations

import numbers
import sys
import types

from legal_core.provider import AnthropicProvider


class _FakeAsyncMessages:
    def __init__(self, captured):
        self._captured = captured

    async def create(self, **kwargs):
        msg = types.SimpleNamespace()
        msg.content = [types.SimpleNamespace(text="metin")]
        msg.usage = types.SimpleNamespace(input_tokens=1, output_tokens=2)
        return msg


class _FakeAsyncClient:
    def __init__(self, **kwargs):
        # Kurulum kwarg'larını sınıf düzeyinde yakala (test bunları inceler).
        _FakeAsyncClient.captured = kwargs
        self.messages = _FakeAsyncMessages(kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _install_fake_anthropic(monkeypatch):
    """anthropic modülünü sahtele — `from anthropic import AsyncAnthropic` bunu bulur."""
    fake_mod = types.ModuleType("anthropic")
    fake_mod.AsyncAnthropic = _FakeAsyncClient
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)


def test_generate_client_built_with_timeout_and_retries(monkeypatch):
    _install_fake_anthropic(monkeypatch)
    provider = AnthropicProvider("sk-x", model="claude-sonnet-4-6", timeout_s=60, max_retries=2)

    # _build_client() doğrudan test et — cache bypass — AsyncAnthropic constructor'ı yakala
    client = provider._build_client()

    assert isinstance(client, _FakeAsyncClient)
    kw = _FakeAsyncClient.captured
    assert kw["max_retries"] == 2
    # Düz float (saniye) — httpx.Timeout DEĞİL (httpx2-SDK reddeder).
    assert isinstance(kw["timeout"], numbers.Real) and not isinstance(kw["timeout"], bool)
    assert kw["timeout"] == 60


def test_defaults_are_bounded(monkeypatch):
    """Varsayılanlar da sınırlı olmalı — timeout/retry hiç 'sonsuz' kalmamalı."""
    _install_fake_anthropic(monkeypatch)
    provider = AnthropicProvider("sk-x")

    # _build_client() doğrudan test et — cache bypass
    provider._build_client()

    kw = _FakeAsyncClient.captured
    assert isinstance(kw["timeout"], numbers.Real) and not isinstance(kw["timeout"], bool)
    assert kw["timeout"] > 0
    assert isinstance(kw["max_retries"], int) and kw["max_retries"] >= 1
