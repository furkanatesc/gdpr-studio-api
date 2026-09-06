import asyncio
from types import SimpleNamespace

from legal_core.provider import AnthropicProvider


class _FakeTextStream:
    def __init__(self, deltas):
        self._deltas = deltas

    def __aiter__(self):
        async def gen():
            for d in self._deltas:
                yield d
        return gen()


class _FakeStreamCM:
    def __init__(self, deltas, usage, stop_reason):
        self.text_stream = _FakeTextStream(deltas)
        self._final = SimpleNamespace(
            usage=SimpleNamespace(input_tokens=usage[0], output_tokens=usage[1]),
            stop_reason=stop_reason,
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get_final_message(self):
        return self._final


class _FakeAsyncClient:
    def __init__(self, cm):
        self.messages = SimpleNamespace(stream=lambda **kw: cm)


def test_astream_deltalari_akitir_ve_last_result_doldurur(monkeypatch):
    p = AnthropicProvider("sk-fake", model="claude-x")
    cm = _FakeStreamCM(["Ay", "dinlatma"], usage=(11, 22), stop_reason="end_turn")
    monkeypatch.setattr(p, "_aclient", lambda: _FakeAsyncClient(cm))

    async def _run():
        return [d async for d in p.astream("PROMPT", max_tokens=100)]

    deltas = asyncio.run(_run())

    assert deltas == ["Ay", "dinlatma"]
    assert p.last_result.input_tokens == 11
    assert p.last_result.output_tokens == 22
    assert p.last_result.stop_reason == "end_turn"
    assert p.last_result.model == "claude-x"
