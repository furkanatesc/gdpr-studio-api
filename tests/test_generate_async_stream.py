import asyncio

from legal_core.generate import generate_aydinlatma_envanter_stream_async
from legal_core.models import ClientProfile
from legal_core.prompt import DISCLAIMER_MARKER
from legal_core.provider import ProviderResult


class FakeAsyncProvider:
    """Ağ yok: prompt'u yakalar, sabit delta'lar akıtır, last_result doldurur."""

    def __init__(self, text="Aydinlatma metni govdesi"):
        self._text = text
        self.model = "fake-model"
        self.last_result = None
        self.seen_prompt = None

    async def astream(self, prompt, *, max_tokens=8000):
        self.seen_prompt = prompt
        for ch in [self._text[:5], self._text[5:]]:
            yield ch
        self.last_result = ProviderResult(
            text="", model="fake-model", input_tokens=10, output_tokens=20, stop_reason="end_turn"
        )


def _collect(sections, boilerplate, profile, provider):
    async def _run():
        return [ev async for ev in generate_aydinlatma_envanter_stream_async(
            sections, boilerplate, profile, provider=provider, max_tokens=8000)]
    return asyncio.run(_run())


def test_async_stream_olay_dizisi_ve_disclaimer():
    provider = FakeAsyncProvider()
    profile = ClientProfile(ad="Test Şirket", unvan="Test Ltd. Şti.")
    boilerplate = {
        "tanimlar": "Test tanımları",
        "ortak_hukumler": "Test ortak hükümler",
        "aktarim_standart": "Test aktarım hükümleri",
        "haklar_m11": "Test haklar m11",
        "basvuru_usulu": "Test başvuru usulü",
        "kaynaklar": "Test kaynakları",
    }
    events = _collect([], boilerplate, profile, provider)  # boş sections: grounding boş liste

    kinds = [k for k, _ in events]
    assert kinds[0] == "grounding"
    assert "delta" in kinds
    assert kinds[-1] == "done"

    # Assertion 1: Grounding VALUE — empty sections yields exactly ("grounding", [])
    grounding_event = events[0]
    assert grounding_event == ("grounding", []), f"Expected ('grounding', []), got {grounding_event}"

    # Assertion 2: Delta verbatim — non-disclaimer deltas reconstruct FakeAsyncProvider text
    # FakeAsyncProvider streams "Aydinlatma metni govdesi" in two chunks: [:5] + [5:]
    deltas = [p for k, p in events if k == "delta"]
    # Remove disclaimer marker from reconstruction if present (it's added as final delta)
    non_disclaimer_deltas = [d for d in deltas if DISCLAIMER_MARKER not in d]
    reconstructed = "".join(non_disclaimer_deltas)
    # The original fake text is "Aydinlatma metni govdesi" (5 + 18 chars)
    expected_text = "Aydinlatma metni govdesi"
    assert reconstructed == expected_text, f"Expected '{expected_text}', got '{reconstructed}'"

    # disclaimer akışta yoksa ('done' öncesi) bir delta olarak eklenir
    full = "".join(p for k, p in events if k == "delta")
    assert DISCLAIMER_MARKER in full

    # Assertion 3: Prompt pass-through — provider.seen_prompt is set (non-empty)
    assert provider.seen_prompt is not None, "provider.seen_prompt should be set by astream()"
    assert provider.seen_prompt, "provider.seen_prompt should be non-empty (built prompt was passed)"

    done_meta = events[-1][1]
    assert done_meta["usage"] == {"inputTokens": 10, "outputTokens": 20}
    assert done_meta["stopReason"] == "end_turn"
    assert done_meta["model"] == "fake-model"
