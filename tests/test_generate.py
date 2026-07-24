from legal_core import GenerateRequest, generate_document
from legal_core.adapters import DictBusinessRuleRepository, DictCategoryRepository
from legal_core.generate import generate_document_stream
from legal_core.grounding import Grounding
from legal_core.prompt import DISCLAIMER_MARKER
from legal_core.provider import ProviderResult

CATEGORIES = {
    "Sağlık Bilgileri": {
        "veri_turu": ["Sağlık raporu"],
        "amaclar": ["Sağlık hizmeti"],
        "hukuki_sebepler": ["6/3 Sağlık, Cinsel Hayat"],
        "kisi_grubu": ["Hasta"],
        "saklama_sureleri": [],
    },
}

RULES = {
    "Tümü": ["Genel kural"],
    "aydinlatma": ["Aydınlatmaya özel kural"],
}


class FakeProvider:
    """Ağ yok: prompt'u yakalar, sabit metin döner."""

    def __init__(self, text="# Aydınlatma Metni\nİçerik."):
        self.text = text
        self.seen_prompt = None

    def generate(self, prompt, *, max_tokens=8000):
        self.seen_prompt = prompt
        return ProviderResult(text=self.text, model="fake-model", input_tokens=10, output_tokens=20)


def _build():
    return (
        Grounding(DictCategoryRepository(CATEGORIES)),
        DictBusinessRuleRepository(RULES),
    )


def test_generate_temel_akis():
    grounding, rules_repo = _build()
    provider = FakeProvider()
    req = GenerateRequest(type="aydinlatma", fields={"sirket": "ACME"}, veriler=["sağlık verisi"])

    res = generate_document(req, grounding=grounding, rules_repo=rules_repo, provider=provider)

    assert res.model == "fake-model"
    assert res.usage.input_tokens == 10 and res.usage.output_tokens == 20
    # Grounding şeffaflığı: sağlık kategorisi yanıta yansımalı
    assert any(g.kategori == "Sağlık Bilgileri" for g in res.grounding)
    # Disclaimer model çıktısında yoksa eklenmeli
    assert DISCLAIMER_MARKER in res.text


def test_prompt_baglayici_kurallari_icerir():
    grounding, rules_repo = _build()
    provider = FakeProvider()
    req = GenerateRequest(type="aydinlatma", fields={}, veriler=["sağlık verisi"])

    generate_document(req, grounding=grounding, rules_repo=rules_repo, provider=provider)
    p = provider.seen_prompt

    assert "DAYANAK UYDURMA YASAĞI" in p  # global kural
    assert "Genel kural" in p and "Aydınlatmaya özel kural" in p  # repo kuralları
    assert "6/3 Sağlık, Cinsel Hayat" in p  # envanter grounding prompt'a girdi


def test_disclaimer_varsa_tekrar_eklenmez():
    grounding, rules_repo = _build()
    provider = FakeProvider(text="Metin\n\n" + "Bu çıktı avukat incelemesine tabi taslaktır.")
    req = GenerateRequest(type="cerez", fields={}, veriler=[])

    res = generate_document(req, grounding=grounding, rules_repo=rules_repo, provider=provider)
    assert res.text.count(DISCLAIMER_MARKER) == 1  # ikinci kez eklenmedi


class FakeStreamProvider:
    """generate_document_stream'in bekledigi duck-type: stream() + last_result."""

    def __init__(self, chunks, model="fake-model", stop_reason=None):
        self.chunks = chunks
        self.model = model
        self.last_result = None
        self._stop_reason = stop_reason

    def stream(self, prompt, *, max_tokens=8000):
        yield from self.chunks
        self.last_result = ProviderResult(
            text="", model=self.model, input_tokens=11, output_tokens=22,
            stop_reason=self._stop_reason,
        )


def test_stream_done_stop_reason_max_tokens_tasir():
    """max_tokens'ta kesilen uretim done meta'sinda gorunur olmali (borc: gorunmez kesme)."""
    grounding, rules_repo = _build()
    provider = FakeStreamProvider(["kirpik cikti"], stop_reason="max_tokens")
    req = GenerateRequest(type="cerez", fields={}, veriler=[])

    events = list(
        generate_document_stream(req, grounding=grounding, rules_repo=rules_repo, provider=provider)
    )
    done = next(e for e in events if e[0] == "done")[1]
    assert done["stopReason"] == "max_tokens"


def test_stream_done_stop_reason_normalde_end_turn():
    grounding, rules_repo = _build()
    provider = FakeStreamProvider(["tam cikti"], stop_reason="end_turn")
    req = GenerateRequest(type="cerez", fields={}, veriler=[])

    events = list(
        generate_document_stream(req, grounding=grounding, rules_repo=rules_repo, provider=provider)
    )
    done = next(e for e in events if e[0] == "done")[1]
    assert done["stopReason"] == "end_turn"


def test_camelcase_serilestirme():
    grounding, rules_repo = _build()
    provider = FakeProvider()
    req = GenerateRequest(type="aydinlatma", fields={}, veriler=["sağlık verisi"])
    res = generate_document(req, grounding=grounding, rules_repo=rules_repo, provider=provider)

    dumped = res.model_dump(by_alias=True)
    assert "hukukiSebepler" in dumped["grounding"][0]  # web kontratı camelCase
    assert "veriTurleri" in dumped["grounding"][0]
