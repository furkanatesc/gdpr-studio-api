"""agenerate() birim testi — async non-stream SDK-response → ProviderResult mapping."""

import asyncio
from types import SimpleNamespace

from legal_core.provider import AnthropicProvider


class _FakeAsyncMessages:
    """Faked AsyncAnthropic().messages — await create() döndürür."""

    def __init__(self, stop_reason):
        self._stop_reason = stop_reason

    async def create(self, **kwargs):
        msg = SimpleNamespace()
        msg.content = [SimpleNamespace(text="agenerate test metin")]
        msg.usage = SimpleNamespace(input_tokens=5, output_tokens=10)
        msg.stop_reason = self._stop_reason
        return msg


class _FakeAsyncClient:
    """Faked AsyncAnthropic istemcisi."""

    def __init__(self, stop_reason="end_turn"):
        self.messages = _FakeAsyncMessages(stop_reason)


def test_agenerate_normal_bitiste_result_text_ve_usage_tasir(monkeypatch):
    """agenerate() message.content[0].text, usage, stop_reason'ı ProviderResult'a taşır."""
    p = AnthropicProvider("sk-fake", model="claude-x")
    fake_client = _FakeAsyncClient("end_turn")

    async def _fake_aclient():
        return fake_client

    monkeypatch.setattr(p, "_aclient", _fake_aclient)

    async def _run():
        return await p.agenerate("PROMPT", max_tokens=100)

    result = asyncio.run(_run())

    assert result.text == "agenerate test metin"
    assert result.input_tokens == 5
    assert result.output_tokens == 10
    assert result.stop_reason == "end_turn"
    assert result.model == "claude-x"
    assert p.last_result == result


def test_agenerate_max_tokensta_stop_reason_tasir(monkeypatch):
    """agenerate() max_tokens kesintisinde stop_reason "max_tokens" olur."""
    p = AnthropicProvider("sk-fake", model="claude-y")
    fake_client = _FakeAsyncClient("max_tokens")

    async def _fake_aclient():
        return fake_client

    monkeypatch.setattr(p, "_aclient", _fake_aclient)

    async def _run():
        return await p.agenerate("PROMPT")

    result = asyncio.run(_run())

    assert result.stop_reason == "max_tokens"
    assert p.last_result.stop_reason == "max_tokens"
