"""AnthropicProvider dayanıklılığı — H1-4 (mimari review P1/güvenilirlik).

Sorun: senkron `def` üretim uçları threadpool'da koşar; Anthropic çağrısında timeout/retry
YOKKEN upstream asılırsa worker + DB bağlantısı ~10 dk tutulur → birkaç asılı çağrı tüm
sync uçları (auth/billing/health) yanıtsız bırakır. Fix: client `timeout` + `max_retries` ile
kurulmalı. Bu test, lazy import edilen `anthropic.Anthropic`'in bu kwarg'larla çağrıldığını
yakalar (ağ yok — client sahte).
"""

from __future__ import annotations

import sys
import types

import httpx

from legal_core.provider import AnthropicProvider, ProviderResult


class _FakeMessages:
    def __init__(self, captured):
        self._captured = captured

    def create(self, **kwargs):
        msg = types.SimpleNamespace()
        msg.content = [types.SimpleNamespace(text="metin")]
        msg.usage = types.SimpleNamespace(input_tokens=1, output_tokens=2)
        return msg


class _FakeClient:
    def __init__(self, **kwargs):
        # Kurulum kwarg'larını sınıf düzeyinde yakala (test bunları inceler).
        _FakeClient.captured = kwargs
        self.messages = _FakeMessages(kwargs)


def _install_fake_anthropic(monkeypatch):
    """anthropic modülünü sahtele — `from anthropic import Anthropic` bunu bulur."""
    fake_mod = types.ModuleType("anthropic")
    fake_mod.Anthropic = _FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)


def test_generate_client_built_with_timeout_and_retries(monkeypatch):
    _install_fake_anthropic(monkeypatch)
    provider = AnthropicProvider("sk-x", model="claude-sonnet-4-6", timeout_s=60, max_retries=2)

    result = provider.generate("prompt", max_tokens=100)

    assert isinstance(result, ProviderResult)
    kw = _FakeClient.captured
    assert kw["max_retries"] == 2
    assert isinstance(kw["timeout"], httpx.Timeout)
    # httpx.Timeout(60) → tüm fazlar 60s
    assert kw["timeout"].read == 60


def test_defaults_are_bounded(monkeypatch):
    """Varsayılanlar da sınırlı olmalı — timeout/retry hiç 'sonsuz' kalmamalı."""
    _install_fake_anthropic(monkeypatch)
    provider = AnthropicProvider("sk-x")
    provider.generate("p", max_tokens=10)
    kw = _FakeClient.captured
    assert isinstance(kw["timeout"], httpx.Timeout)
    assert kw["timeout"].read is not None and kw["timeout"].read > 0
    assert isinstance(kw["max_retries"], int) and kw["max_retries"] >= 1
