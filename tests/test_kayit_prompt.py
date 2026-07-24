from __future__ import annotations

from legal_core.generate import generate_kayit_envanter_stream
from legal_core.models import ClientProfile, ProcessRecord
from legal_core.prompt import DISCLAIMER, ONAY_BEKLEYEN_PLACEHOLDER, build_kayit_envanter_prompt
from legal_core.provider import ProviderResult

PROFILE = ClientProfile(ad="ACME A.S.", unvan="ACME Anonim Sirketi", adres="Istanbul", kep="acme@hs01.kep.tr")
RECORDS = [
    ProcessRecord(
        departman="Insan Kaynaklari", is_sureci="Ozluk Yonetimi", alt_surec="Bordro",
        kisi_grubu="Calisan", kategoriler=["Kimlik", "Finans"], veri_turleri=["Ad Soyad"],
        amaclar=["Bordro islemleri"], hukuki_sebepler=["m.5/2-c"], saklama_sureleri=["10 yil"],
        aktarim=["SGK"], idari_tedbirler=["Erisim yetki"], teknik_tedbirler=["Sifreleme"],
    ),
]
MEASURES = ["Erisim loglari tutulur", "Veriler sifrelenir"]
RULES = ["Kayit VERBIS unsurlarini icermeli: amac, kategori, kisi grubu, alici, saklama."]


def test_kayit_prompt_icerir_kimlik_surec_tedbir_kural():
    p = build_kayit_envanter_prompt(RECORDS, PROFILE, MEASURES, RULES)
    assert "ACME Anonim Sirketi" in p          # kimlik profilden
    assert "Ozluk Yonetimi" in p               # surec (format_processes)
    assert "Calisan" in p                       # kisi grubu
    assert "m.5/2-c" in p                        # hukuki sebep
    assert "10 yil" in p                         # saklama
    assert "SGK" in p                            # alici/aktarim
    assert "Veriler sifrelenir" in p            # tedbir
    assert "VERBIS unsurlarini icermeli" in p   # is kurali


def test_kayit_prompt_uydurma_yasagi_ve_disclaimer():
    p = build_kayit_envanter_prompt(RECORDS, PROFILE, MEASURES, RULES)
    assert "UYDURMA" in p
    assert DISCLAIMER in p


def test_kayit_prompt_bos_envanter_uyari():
    p = build_kayit_envanter_prompt([], PROFILE, MEASURES, RULES)
    assert "Envanterde süreç yok" in p or "surec yok" in p.lower()


def test_kayit_prompt_bos_zorunlu_alanlar_kosulsuz_placeholder_ile_gorunur():
    """C1: hukuki sebep + aktarım + amaç boşsa satır hiç düşmemeli — koşulsuz placeholder basılmalı."""
    rec = ProcessRecord(
        departman="Insan Kaynaklari", is_sureci="Ozluk Yonetimi", alt_surec="Bordro",
        kisi_grubu="Calisan", kategoriler=["Kimlik"], veri_turleri=["Ad Soyad"],
        amaclar=[], hukuki_sebepler=[], saklama_sureleri=["10 yil"], aktarim=[],
    )
    p = build_kayit_envanter_prompt([rec], PROFILE, MEASURES, RULES)
    assert f"İşleme Amaçları: {ONAY_BEKLEYEN_PLACEHOLDER}" in p
    assert f"Hukuki Sebep: {ONAY_BEKLEYEN_PLACEHOLDER}" in p
    assert f"Alıcı/Aktarım: {ONAY_BEKLEYEN_PLACEHOLDER}" in p


def test_kayit_prompt_tum_zorunlu_slotlar_bos_kayit_ise_placeholder_basar():
    """Puan A'nın saydığı 6 zorunlu VERBİS slotunun hepsi kısı grubu dahil kapsanmalı."""
    rec = ProcessRecord(
        departman="", is_sureci="", alt_surec="", kisi_grubu="",
        kategoriler=[], veri_turleri=[], amaclar=[], hukuki_sebepler=[],
        saklama_sureleri=[], aktarim=[],
    )
    p = build_kayit_envanter_prompt([rec], PROFILE, MEASURES, RULES)
    assert f"Veri Konusu Kişi Grubu: {ONAY_BEKLEYEN_PLACEHOLDER}" in p
    assert f"Kişisel Veri Kategorisi/Türü: {ONAY_BEKLEYEN_PLACEHOLDER}" in p
    assert f"İşleme Amaçları: {ONAY_BEKLEYEN_PLACEHOLDER}" in p
    assert f"Hukuki Sebep: {ONAY_BEKLEYEN_PLACEHOLDER}" in p
    assert f"Saklama Süresi: {ONAY_BEKLEYEN_PLACEHOLDER}" in p
    assert f"Alıcı/Aktarım: {ONAY_BEKLEYEN_PLACEHOLDER}" in p


def test_kayit_prompt_kirpma_sessiz_degil():
    many = [
        ProcessRecord(
            departman="IK", is_sureci="Ozluk", alt_surec=f"Adim {i}", kisi_grubu="Calisan",
            kategoriler=["Kimlik"], amaclar=["Amac"], hukuki_sebepler=["m.5"],
            saklama_sureleri=["1 yil"], aktarim=["Yok"],
        )
        for i in range(65)
    ]
    p = build_kayit_envanter_prompt(many, PROFILE, MEASURES, RULES, process_cap=60)
    assert "Adim 0" in p and "Adim 59" in p
    assert "Adim 60" not in p
    assert "65" in p and "kırpıldı" in p.lower()


class _FakeStreamProvider:
    def __init__(self, chunks, model="fake-model"):
        self.chunks = chunks
        self.model = model
        self.last_result = None

    def stream(self, prompt, *, max_tokens=8000):
        self.seen_prompt = prompt
        yield from self.chunks
        self.last_result = ProviderResult(text="", model=self.model, input_tokens=11, output_tokens=22)


def test_kayit_stream_olay_sirasi_ve_grounding():
    provider = _FakeStreamProvider(["Isleme ", "kaydi."])
    events = list(generate_kayit_envanter_stream(RECORDS, PROFILE, MEASURES, RULES, provider=provider))
    kinds = [e[0] for e in events]
    assert kinds[0] == "grounding"
    assert kinds[-1] == "done"
    assert kinds.count("delta") >= 2
    grounding = events[0][1]
    assert len(grounding) == 1
    assert grounding[0].kategori == "Ozluk Yonetimi"  # is_sureci


def test_kayit_stream_disclaimer_garantisi():
    provider = _FakeStreamProvider(["kisa cikti"])
    events = list(generate_kayit_envanter_stream(RECORDS, PROFILE, MEASURES, RULES, provider=provider))
    full = "".join(e[1] for e in events if e[0] == "delta")
    assert "avukat incelemesine tabi" in full


def test_kayit_stream_grounding_cap_ile_prompt_tutarli():
    """Grounding olayı, promptun (format_kayit_processes) gerçekte gösterdiği kayıt
    sayısıyla eşleşmeli — şeffaflık paneli belgeye girmeyen satırları göstermemeli."""
    many = [
        ProcessRecord(
            departman="IK", is_sureci="Ozluk", alt_surec=f"Adim {i}", kisi_grubu="Calisan",
            kategoriler=["Kimlik"], amaclar=["Amac"], hukuki_sebepler=["m.5"],
            saklama_sureleri=["1 yil"], aktarim=["Yok"],
        )
        for i in range(65)
    ]
    provider = _FakeStreamProvider(["cikti"])
    events = list(
        generate_kayit_envanter_stream(many, PROFILE, MEASURES, RULES, provider=provider, process_cap=60)
    )
    grounding = events[0][1]
    assert len(grounding) == 60


def test_kayit_stream_grounding_cap_sifir_sinirsiz():
    """process_cap=0 sınırsız demektir — grounding TÜM kayıtları yayınlamalı (prompt ile tutarlı)."""
    many = [
        ProcessRecord(
            departman="IK", is_sureci="Ozluk", alt_surec=f"Adim {i}", kisi_grubu="Calisan",
            kategoriler=["Kimlik"], amaclar=["Amac"], hukuki_sebepler=["m.5"],
            saklama_sureleri=["1 yil"], aktarim=["Yok"],
        )
        for i in range(65)
    ]
    provider = _FakeStreamProvider(["cikti"])
    events = list(
        generate_kayit_envanter_stream(many, PROFILE, MEASURES, RULES, provider=provider, process_cap=0)
    )
    grounding = events[0][1]
    assert len(grounding) == 65
