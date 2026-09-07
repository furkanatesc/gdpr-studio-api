import asyncio
import json

import pytest

from legal_core.dpa_review import (
    DPA_CHECKLIST,
    DpaReviewResult,
    ReviewContext,
    ReviewItem,
    ReviewParseError,
    build_dpa_review_prompt,
    parse_review_json,
    review_dpa,
)


def test_checklist_has_expected_items():
    assert len(DPA_CHECKLIST) == 11
    assert all(isinstance(it, ReviewItem) for it in DPA_CHECKLIST)


def test_checklist_ids_unique_and_nonempty():
    ids = [it.id for it in DPA_CHECKLIST]
    assert len(ids) == len(set(ids))
    assert all(it.id and it.baslik and it.kvkk_ref and it.aranan for it in DPA_CHECKLIST)


def test_three_red_flags_present():
    flags = [it for it in DPA_CHECKLIST if it.kirmizi_bayrak]
    assert len(flags) == 3
    flag_ids = {it.id for it in flags}
    assert {"ihlal_bildirim", "sozlesme_sonu", "kendi_amaci"} <= flag_ids


def _ctx(yurt_disi=False):
    return ReviewContext(
        veri_sorumlusu="Acme A.Ş.", isleyen_adi="Bulut Ltd.",
        yurt_disi=yurt_disi, aktarim_adlari=["Bulut Ltd."], kategoriler=["Kimlik"],
    )


def test_prompt_includes_context_and_all_items():
    prompt = build_dpa_review_prompt("örnek sözleşme metni", _ctx(yurt_disi=True))
    assert "Acme A.Ş." in prompt
    assert "örnek sözleşme metni" in prompt
    assert "yurt dışı" in prompt.lower()
    for it in DPA_CHECKLIST:
        assert it.id in prompt


def test_parse_fills_missing_items_as_yetersiz():
    raw = json.dumps([{"madde_id": "gizlilik", "durum": "var",
                       "alinti": "Madde 5...", "gerekce": "mevcut", "oneri": ""}])
    findings = parse_review_json(raw)
    assert len(findings) == 11
    by_id = {f.madde_id: f for f in findings}
    assert by_id["gizlilik"].durum == "var"
    assert by_id["belgeli_talimat"].durum == "yetersiz"


def test_parse_strips_code_fence():
    raw = "```json\n[]\n```"
    findings = parse_review_json(raw)
    assert len(findings) == 11


def test_parse_invalid_json_raises():
    with pytest.raises(ReviewParseError):
        parse_review_json("bu json değil")


class _FakeProvider:
    def __init__(self, payload: str):
        self._payload = payload
        self.model = "fake"
        self.calls = 0

    async def astream(self, prompt, *, max_tokens=8000):
        self.calls += 1
        # akışı taklit için parça parça yield
        mid = len(self._payload) // 2
        yield self._payload[:mid]
        yield self._payload[mid:]


def test_review_dpa_counts_summary():
    payload = json.dumps([
        {"madde_id": it.id,
         "durum": ("var" if i % 3 == 0 else "eksik" if i % 3 == 1 else "yetersiz"),
         "alinti": "", "gerekce": "g", "oneri": "o"}
        for i, it in enumerate(DPA_CHECKLIST)
    ])
    result = asyncio.run(review_dpa("metin", _ctx(), provider=_FakeProvider(payload)))
    assert isinstance(result, DpaReviewResult)
    assert result.uygun + result.eksik + result.yetersiz == 11
    assert result.kirmizi_bayrak >= 0
    assert result.disclaimer


def test_review_dpa_retries_once_on_bad_json():
    # İlk çağrı bozuk, ama _FakeProvider hep aynı payload döndürür → retry de bozuk → ReviewParseError.
    bad = _FakeProvider("bu json değil")
    with pytest.raises(ReviewParseError):
        asyncio.run(review_dpa("metin", _ctx(), provider=bad))
    assert bad.calls == 2  # bir asıl + bir retry
