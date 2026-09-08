"""stop_reason gorunurlugu - max_tokens'ta kesilen uretim sessiz kalmamali.

Sorun: ProviderResult'ta stop_reason YOKTU ve AnthropicProvider bunu Anthropic
yanitindan hic okumuyordu. Sonuc: max_tokens tavaninda kesilen bir metin,
disclaimer'la "bitmis" gorunup tam puanla saklaniyordu - kesinti gorunmezdi.
Bu test: agenerate() ve astream() ikisi de stop_reason'i ProviderResult'a tasir.
"""

from __future__ import annotations

import asyncio
import sys
import types

from legal_core.provider import AnthropicProvider, ProviderResult


def test_provider_result_stop_reason_varsayilani_none():
    r = ProviderResult(text="x", model="m")
    assert r.stop_reason is None


class _FakeAsyncMessages:
    def __init__(self, stop_reason):
        self._stop_reason = stop_reason

    async def create(self, **kwargs):
        msg = types.SimpleNamespace()
        msg.content = [types.SimpleNamespace(text="metin")]
        msg.usage = types.SimpleNamespace(input_tokens=1, output_tokens=2)
        msg.stop_reason = self._stop_reason
        return msg


class _FakeAsyncClient:
    def __init__(self, stop_reason="end_turn", **kwargs):
        self.messages = _FakeAsyncMessages(stop_reason)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _install_fake_anthropic(monkeypatch, stop_reason):
    fake_mod = types.ModuleType("anthropic")
    fake_mod.AsyncAnthropic = lambda **kw: _FakeAsyncClient(stop_reason=stop_reason)
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)


def test_generate_max_tokensta_stop_reason_tasir(monkeypatch):
    _install_fake_anthropic(monkeypatch, "max_tokens")
    provider = AnthropicProvider("sk-x")

    result = asyncio.run(provider.agenerate("prompt"))

    assert result.stop_reason == "max_tokens"


def test_generate_normal_bitiste_stop_reason_end_turn(monkeypatch):
    _install_fake_anthropic(monkeypatch, "end_turn")
    provider = AnthropicProvider("sk-x")

    result = asyncio.run(provider.agenerate("prompt"))

    assert result.stop_reason == "end_turn"


class _FakeStreamCtx:
    def __init__(self, stop_reason):
        self._stop_reason = stop_reason

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        async def gen():
            yield "parca"
        return gen()

    async def get_final_message(self):
        msg = types.SimpleNamespace()
        msg.usage = types.SimpleNamespace(input_tokens=3, output_tokens=4)
        msg.stop_reason = self._stop_reason
        return msg


class _FakeAsyncMessagesStream:
    def __init__(self, stop_reason):
        self._stop_reason = stop_reason

    def stream(self, **kwargs):
        return _FakeStreamCtx(self._stop_reason)


class _FakeAsyncClientStream:
    def __init__(self, stop_reason, **kwargs):
        self.messages = _FakeAsyncMessagesStream(stop_reason)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


def _install_fake_anthropic_stream(monkeypatch, stop_reason):
    fake_mod = types.ModuleType("anthropic")
    fake_mod.AsyncAnthropic = lambda **kw: _FakeAsyncClientStream(stop_reason)
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)


def test_stream_max_tokensta_last_result_stop_reason_tasir(monkeypatch):
    _install_fake_anthropic_stream(monkeypatch, "max_tokens")
    provider = AnthropicProvider("sk-x")

    async def _run():
        return [d async for d in provider.astream("prompt")]

    chunks = asyncio.run(_run())

    assert chunks == ["parca"]
    assert provider.last_result.stop_reason == "max_tokens"


def test_stream_normal_bitiste_last_result_stop_reason_end_turn(monkeypatch):
    _install_fake_anthropic_stream(monkeypatch, "end_turn")
    provider = AnthropicProvider("sk-x")

    async def _run():
        return [d async for d in provider.astream("prompt")]

    asyncio.run(_run())

    assert provider.last_result.stop_reason == "end_turn"
