"""Aydinlatma-envanter uretim modu: prompt + stream (Faz 2.2 T4).

Kritik regresyon-onleyici test: bir section'in bir alani bos olsa bile prompt'ta
o basligin adi + placeholder gecer (koşullu atlama YOK — sahadaki hatanin cozumu).
"""

from __future__ import annotations

from legal_core.aggregate_sections import Section
from legal_core.generate import generate_aydinlatma_envanter_stream
from legal_core.models import ClientProfile
from legal_core.prompt import DISCLAIMER, build_aydinlatma_envanter_prompt
from legal_core.provider import ProviderResult

PLACEHOLDER = "[Avukat tarafından doldurulacak]"

BOILERPLATE = {
    "tanimlar": "Tanimlar metni - ayirt edici ifade TANIMLAR-IZ",
    "kaynaklar": "Kaynaklar metni - ayirt edici ifade KAYNAKLAR-IZ",
    "ortak_hukumler": "Ortak hukumler metni - ayirt edici ifade ORTAK-HUKUMLER-IZ",
    "haklar_m11": "Haklar m.11 metni - ayirt edici ifade HAKLAR-M11-IZ",
    "basvuru_usulu": "Basvuru usulu metni - ayirt edici ifade BASVURU-USULU-IZ",
    "aktarim_standart": "Standart aktarim metni - ayirt edici ifade AKTARIM-STD-IZ",
}

PROFILE = ClientProfile(
    ad="ACME A.S.",
    unvan="ACME Anonim Sirketi",
    adres="Istanbul",
    mersis="1234567890123456",
    vergi_dairesi="Kadikoy",
    vergi_no="1234567890",
    kep="acme@hs01.kep.tr",
    eposta="kvkk@acme.com",
    telefon="02121234567",
)

SECTIONS = [
    Section(
        is_sureci="Insan Kaynaklari",
        kisi_gruplari=["Calisan"],
        kategoriler=["Kimlik"],
        veri_turleri=["Ad Soyad"],
        amaclar=["Bordro islemleri"],
        hukuki_sebepler=["m.5/2-c Sozlesmenin kurulmasi", "m.6 acik riza"],
        saklama_sureleri=[],  # BOS - regresyon testinin odagi
        aktarim=[],
        toplama=[],
    ),
    Section(
        is_sureci="Musteri Iliskileri",
        kisi_gruplari=["Musteri"],
        kategoriler=["Iletisim"],
        veri_turleri=["Telefon"],
        amaclar=["Musteri destegi"],
        hukuki_sebepler=[],  # BOS
        saklama_sureleri=["10 yil"],
        aktarim=[],
        toplama=[],
    ),
]


class FakeStreamProvider:
    """AnthropicProvider.stream() desenini taklit eder: delta akitir, sonda last_result yazar."""

    def __init__(self, chunks, model="fake-model", input_tokens=11, output_tokens=22, stop_reason=None):
        self.chunks = chunks
        self.model = model
        self.last_result = None
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens
        self._stop_reason = stop_reason
        self.seen_prompt = None

    def stream(self, prompt, *, max_tokens=8000):
        self.seen_prompt = prompt
        yield from self.chunks
        self.last_result = ProviderResult(
            text="", model=self.model,
            input_tokens=self._input_tokens, output_tokens=self._output_tokens,
            stop_reason=self._stop_reason,
        )


def test_prompt_icerir_alti_baslik_talimati_ve_uydurma_uyarisi():
    p = build_aydinlatma_envanter_prompt(SECTIONS, BOILERPLATE, PROFILE)

    assert "UYDURMA" in p
    assert "İşlenen kişisel veriler" in p
    assert "İşleme amaçları" in p
    assert "Hukuki sebep" in p
    assert "Saklama süresi" in p
    assert "Aktarım" in p
    assert "Toplama yöntemi" in p


def test_prompt_her_iki_is_surecini_icerir():
    p = build_aydinlatma_envanter_prompt(SECTIONS, BOILERPLATE, PROFILE)

    assert "Insan Kaynaklari" in p
    assert "Musteri Iliskileri" in p


def test_prompt_bos_alan_kosulsuz_placeholder_ile_basilir():
    """Kritik regresyon testi: saklama_sureleri BOS olan bolumde baslik+placeholder yine de var."""
    p = build_aydinlatma_envanter_prompt(SECTIONS, BOILERPLATE, PROFILE)

    ik_start = p.index("Insan Kaynaklari")
    ik_end = p.index("Musteri Iliskileri")
    ik_block = p[ik_start:ik_end]

    assert "Saklama süresi:" in ik_block
    assert PLACEHOLDER in ik_block

    musteri_block = p[ik_end:]
    assert "Hukuki sebep:" in musteri_block
    assert PLACEHOLDER in musteri_block


def test_prompt_dolu_hukuki_sebep_madde_atiflarini_korur():
    p = build_aydinlatma_envanter_prompt(SECTIONS, BOILERPLATE, PROFILE)
    assert "m.5/2-c Sozlesmenin kurulmasi" in p
    assert "m.6 acik riza" in p


def test_prompt_boilerplate_izlerini_icerir():
    p = build_aydinlatma_envanter_prompt(SECTIONS, BOILERPLATE, PROFILE)
    assert "TANIMLAR-IZ" in p
    assert "KAYNAKLAR-IZ" in p
    assert "ORTAK-HUKUMLER-IZ" in p
    assert "HAKLAR-M11-IZ" in p
    assert "BASVURU-USULU-IZ" in p
    assert "AKTARIM-STD-IZ" in p


def test_prompt_saklama_arsiv_cerceve_talimati_var():
    """S1: saklama süresi açıkça yazılır + 'Saklama ve Arşiv Faaliyetleri' çerçevesi (avukat)."""
    p = build_aydinlatma_envanter_prompt(SECTIONS, BOILERPLATE, PROFILE)
    assert "Saklama ve\nArşiv Faaliyetlerinin Yürütülmesi" in p or "Saklama ve Arşiv Faaliyetlerinin Yürütülmesi" in p
    assert "AÇIKÇA yaz" in p


def test_prompt_bos_aktarimda_standart_aktarim_talimati_var():
    """PROGSA kiyas Bulgu 4: envanterde aktarim bos olsa da standart aktarim hukumleri
    prompt'ta yer alir ve model bos aktarimda bunu uygulamaya yonlendirilir."""
    p = build_aydinlatma_envanter_prompt(SECTIONS, BOILERPLATE, PROFILE)
    assert "AKTARIM-STD-IZ" in p
    assert "Standart Aktarım" in p


def test_prompt_amac_hukuki_eslestirme_talimati_var():
    """S3: her amaci envanterdeki EN UYGUN hukuki sebeple eslestir + parantez ici gerekce;
    yeni hukuki sebep UYDURMA (avukat: sistem denesin, avukat duzeltir)."""
    p = build_aydinlatma_envanter_prompt(SECTIONS, BOILERPLATE, PROFILE)
    assert "eşleştir" in p
    assert "gerekçe" in p
    assert "yeni bir hukuki sebep" in p


def test_prompt_kaynaklar_envanter_toplamadan_turer():
    """kaynaklar müvekkil-özel (avukat: 'kaynaklar müvekkile göre değişir'): toplama dolu
    bölümler varsa belge-düzeyi Veri Toplama Kaynakları envanterden türer, boilerplate'e düşmez."""
    sections = [
        Section(is_sureci="A", toplama=["Web formu", "Cagri merkezi"]),
        Section(is_sureci="B", toplama=["Web formu", "E-posta"]),
    ]
    p = build_aydinlatma_envanter_prompt(sections, BOILERPLATE, PROFILE)
    assert "Web formu" in p
    assert "Cagri merkezi" in p
    assert "E-posta" in p
    kaynak_idx = p.index("Veri Toplama Kaynakları")
    ortak_idx = p.index("Ortak Hükümler")
    assert "KAYNAKLAR-IZ" not in p[kaynak_idx:ortak_idx]


def test_prompt_kaynaklar_toplama_bos_ise_boilerplate():
    """toplama tüm bölümlerde boşsa belge-düzeyi kaynaklar boilerplate'e düşer (uydurma yok)."""
    sections = [Section(is_sureci="A", toplama=[])]
    p = build_aydinlatma_envanter_prompt(sections, BOILERPLATE, PROFILE)
    kaynak_idx = p.index("Veri Toplama Kaynakları")
    ortak_idx = p.index("Ortak Hükümler")
    assert "KAYNAKLAR-IZ" in p[kaynak_idx:ortak_idx]


def test_prompt_disclaimer_talimati_icerir():
    p = build_aydinlatma_envanter_prompt(SECTIONS, BOILERPLATE, PROFILE)
    assert DISCLAIMER in p


def test_prompt_profil_alani_none_ise_placeholder():
    bos_profil = ClientProfile(ad="ACME")
    p = build_aydinlatma_envanter_prompt(SECTIONS, BOILERPLATE, bos_profil)

    assert PLACEHOLDER in p
    # Unvan alani None birakildi -> placeholder ile gorunmeli
    unvan_line_idx = p.index("Unvan")
    assert PLACEHOLDER in p[unvan_line_idx:unvan_line_idx + 200]


def test_prompt_bos_sections_uyari_satiri_koyar():
    p = build_aydinlatma_envanter_prompt([], BOILERPLATE, PROFILE)
    assert "envanterde iş süreci bulunamadı" in p or "iş süreci bulunamadı" in p


def test_stream_olay_sirasi_ve_grounding():
    provider = FakeStreamProvider(["Merhaba ", "dunya."])
    events = list(
        generate_aydinlatma_envanter_stream(
            SECTIONS, BOILERPLATE, PROFILE, provider=provider,
        )
    )

    kinds = [e[0] for e in events]
    assert kinds[0] == "grounding"
    assert kinds[-1] == "done"
    assert all(k in ("grounding", "delta", "done") for k in kinds)
    assert kinds.count("delta") >= 2

    grounding_records = events[0][1]
    assert len(grounding_records) == 2
    assert grounding_records[0].kategori == "Insan Kaynaklari"
    assert grounding_records[1].kategori == "Musteri Iliskileri"


def test_stream_done_disclaimer_ve_usage_icerir():
    provider = FakeStreamProvider(["Bir metin parcasi."])
    events = list(
        generate_aydinlatma_envanter_stream(
            SECTIONS, BOILERPLATE, PROFILE, provider=provider,
        )
    )

    done = dict(events)["done"] if False else next(e for e in events if e[0] == "done")[1]
    assert done["disclaimer"] == DISCLAIMER
    assert done["model"] == "fake-model"
    assert done["usage"]["inputTokens"] == 11
    assert done["usage"]["outputTokens"] == 22


def test_stream_done_stop_reason_max_tokens_tasir():
    """max_tokens'ta kesilen uretim done meta'sinda gorunur olmali (borc: gorunmez kesme)."""
    provider = FakeStreamProvider(["kirpik cikti"], stop_reason="max_tokens")
    events = list(
        generate_aydinlatma_envanter_stream(SECTIONS, BOILERPLATE, PROFILE, provider=provider)
    )
    done = next(e for e in events if e[0] == "done")[1]
    assert done["stopReason"] == "max_tokens"


def test_stream_done_stop_reason_normalde_end_turn():
    provider = FakeStreamProvider(["tam cikti"], stop_reason="end_turn")
    events = list(
        generate_aydinlatma_envanter_stream(SECTIONS, BOILERPLATE, PROFILE, provider=provider)
    )
    done = next(e for e in events if e[0] == "done")[1]
    assert done["stopReason"] == "end_turn"


def test_stream_final_metin_disclaimer_garantisi():
    """Fake model disclaimer uretmese bile ensure_disclaimer ile eklenir (delta kuyrugu)."""
    provider = FakeStreamProvider(["kisa model ciktisi"])
    events = list(
        generate_aydinlatma_envanter_stream(
            SECTIONS, BOILERPLATE, PROFILE, provider=provider,
        )
    )

    full_text = "".join(e[1] for e in events if e[0] == "delta")
    assert "avukat incelemesine tabi" in full_text
