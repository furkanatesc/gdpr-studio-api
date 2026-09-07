"""AnthropicProvider dayanıklılığı — H1-4 (mimari review P1/güvenilirlik).

Sorun: Anthropic çağrısında timeout/retry YOKKEN upstream asılırsa event loop + DB
bağlantısı ~10 dk tutulur → birkaç asılı çağrı isteği yanıtsız bırakır. Fix: client
`timeout` + `max_retries` ile kurulmalı. Bu test, lazy import edilen
`anthropic.AsyncAnthropic`'in bu kwarg'larla çağrıldığını yakalar (ağ yok — client sahte).
"""

from __future__ import annotations

import asyncio
import sys
import types

import httpx

from legal_core.provider import AnthropicProvider, ProviderResult


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


def _install_fake_anthropic(monkeypatch):
    """anthropic modülünü sahtele — `from anthropic import AsyncAnthropic` bunu bulur."""
    fake_mod = types.ModuleType("anthropic")
    fake_mod.AsyncAnthropic = _FakeAsyncClient
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)


def test_generate_client_built_with_timeout_and_retries(monkeypatch):
    _install_fake_anthropic(monkeypatch)
    provider = AnthropicProvider("sk-x", model="claude-sonnet-4-6", timeout_s=60, max_retries=2)

    result = asyncio.run(provider.agenerate("prompt", max_tokens=100))

    assert isinstance(result, ProviderResult)
    kw = _FakeAsyncClient.captured
    assert kw["max_retries"] == 2
    assert isinstance(kw["timeout"], httpx.Timeout)
    # httpx.Timeout(60) → tüm fazlar 60s
    assert kw["timeout"].read == 60


def test_defaults_are_bounded(monkeypatch):
    """Varsayılanlar da sınırlı olmalı — timeout/retry hiç 'sonsuz' kalmamalı."""
    _install_fake_anthropic(monkeypatch)
    provider = AnthropicProvider("sk-x")
    asyncio.run(provider.agenerate("p", max_tokens=10))
    kw = _FakeAsyncClient.captured
    assert isinstance(kw["timeout"], httpx.Timeout)
    assert kw["timeout"].read is not None and kw["timeout"].read > 0
    assert isinstance(kw["max_retries"], int) and kw["max_retries"] >= 1
