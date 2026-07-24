from __future__ import annotations

from legal_core.models import ClientProfile, ProcessRecord
from legal_core.prompt import DISCLAIMER, build_kayit_envanter_prompt

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
    assert "Veriler sifrelenir" in p            # tedbir
    assert "VERBIS unsurlarini icermeli" in p   # is kurali


def test_kayit_prompt_uydurma_yasagi_ve_disclaimer():
    p = build_kayit_envanter_prompt(RECORDS, PROFILE, MEASURES, RULES)
    assert "UYDURMA" in p
    assert DISCLAIMER in p


def test_kayit_prompt_bos_envanter_uyari():
    p = build_kayit_envanter_prompt([], PROFILE, MEASURES, RULES)
    assert "Envanterde süreç yok" in p or "surec yok" in p.lower()
