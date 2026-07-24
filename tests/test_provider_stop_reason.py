"""stop_reason gorunurlugu - max_tokens'ta kesilen uretim sessiz kalmamali.

Sorun: ProviderResult'ta stop_reason YOKTU ve AnthropicProvider bunu Anthropic
yanitindan hic okumuyordu. Sonuc: max_tokens tavaninda kesilen bir metin,
disclaimer'la "bitmis" gorunup tam puanla saklaniyordu - kesinti gorunmezdi.
Bu test: generate() ve stream() ikisi de stop_reason'i ProviderResult'a tasir.
"""

from __future__ import annotations

import sys
import types

from legal_core.provider import AnthropicProvider, ProviderResult


def test_provider_result_stop_reason_varsayilani_none():
    r = ProviderResult(text="x", model="m")
    assert r.stop_reason is None


class _FakeMessages:
    def __init__(self, stop_reason):
        self._stop_reason = stop_reason

    def create(self, **kwargs):
        msg = types.SimpleNamespace()
        msg.content = [types.SimpleNamespace(text="metin")]
        msg.usage = types.SimpleNamespace(input_tokens=1, output_tokens=2)
        msg.stop_reason = self._stop_reason
        return msg


class _FakeClient:
    def __init__(self, stop_reason="end_turn", **kwargs):
        self.messages = _FakeMessages(stop_reason)


def _install_fake_anthropic(monkeypatch, stop_reason):
    fake_mod = types.ModuleType("anthropic")
    fake_mod.Anthropic = lambda **kw: _FakeClient(stop_reason=stop_reason)
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)


def test_generate_max_tokensta_stop_reason_tasir(monkeypatch):
    _install_fake_anthropic(monkeypatch, "max_tokens")
    provider = AnthropicProvider("sk-x")

    result = provider.generate("prompt")

    assert result.stop_reason == "max_tokens"


def test_generate_normal_bitiste_stop_reason_end_turn(monkeypatch):
    _install_fake_anthropic(monkeypatch, "end_turn")
    provider = AnthropicProvider("sk-x")

    result = provider.generate("prompt")

    assert result.stop_reason == "end_turn"


class _FakeStreamCtx:
    def __init__(self, stop_reason):
        self._stop_reason = stop_reason

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def text_stream(self):
        yield "parca"

    def get_final_message(self):
        msg = types.SimpleNamespace()
        msg.usage = types.SimpleNamespace(input_tokens=3, output_tokens=4)
        msg.stop_reason = self._stop_reason
        return msg


class _FakeMessagesStream:
    def __init__(self, stop_reason):
        self._stop_reason = stop_reason

    def stream(self, **kwargs):
        return _FakeStreamCtx(self._stop_reason)


class _FakeClientStream:
    def __init__(self, stop_reason, **kwargs):
        self.messages = _FakeMessagesStream(stop_reason)


def _install_fake_anthropic_stream(monkeypatch, stop_reason):
    fake_mod = types.ModuleType("anthropic")
    fake_mod.Anthropic = lambda **kw: _FakeClientStream(stop_reason)
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)


def test_stream_max_tokensta_last_result_stop_reason_tasir(monkeypatch):
    _install_fake_anthropic_stream(monkeypatch, "max_tokens")
    provider = AnthropicProvider("sk-x")

    chunks = list(provider.stream("prompt"))

    assert chunks == ["parca"]
    assert provider.last_result.stop_reason == "max_tokens"


def test_stream_normal_bitiste_last_result_stop_reason_end_turn(monkeypatch):
    _install_fake_anthropic_stream(monkeypatch, "end_turn")
    provider = AnthropicProvider("sk-x")

    list(provider.stream("prompt"))

    assert provider.last_result.stop_reason == "end_turn"
