"""Golden set — temsili senaryolar + beklenen hukuki özellikler.

Küçük ama kapsayıcı tutuldu (özel nitelikli veri, çerez/rıza, DPIA risk, ihlal/72saat).
Her senaryo gerçek üretimden geçirilip checks.py kontrollerine tabi tutulur.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from legal_core import GenerateRequest


@dataclass
class EvalCase:
    name: str
    request: GenerateRequest
    # Deterministik: bu kategoriler grounding'de çözülmeli (alt küme yeterli).
    expected_grounding: set[str] = field(default_factory=set)
    # Model çıktısı kontrolleri:
    articles: list[int] = field(default_factory=list)
    sections: list[str] = field(default_factory=list)
    special_category: bool = False
    retention_placeholder: bool = False


GOLDEN: list[EvalCase] = [
    EvalCase(
        name="aydinlatma_saglik",
        request=GenerateRequest(
            type="aydinlatma",
            fields={"sirket": "Yaşam Hastaneleri A.Ş.", "email": "kvkk@yasam.com", "sektor": "Sağlık / Medikal"},
            veriler=["Ad-Soyad", "TC Kimlik No", "Sağlık verisi", "E-posta"],
            amaclar=["Hizmet sunumu", "Yasal yükümlülük"],
        ),
        expected_grounding={"Kimlik", "Sağlık Bilgileri", "İletişim"},
        articles=[5, 6, 10, 11],  # KVKK m.5/6/10/11
        sections=["aydınlatma", "hak"],
        special_category=True,        # sağlık verisi → m.6
        retention_placeholder=True,   # envanterde saklama süresi boş
    ),
    EvalCase(
        name="cerez_politikasi",
        request=GenerateRequest(
            type="cerez",
            fields={"site": "www.test.com", "sirket": "Test A.Ş."},
            veriler=["Analitik çerezler", "Pazarlama çerezleri"],
        ),
        expected_grounding=set(),  # çerez türleri envanter kategorisi değil → grounding boş (beklenen)
        articles=[],
        sections=["çerez", "açık rıza"],
        special_category=False,
        retention_placeholder=False,
    ),
    EvalCase(
        name="dpia_profilleme",
        request=GenerateRequest(
            type="dpia",
            fields={"proje": "Müşteri Profilleme Sistemi", "kapsam": "Otomatik karar ve sağlık verisi işleme"},
            veriler=["Profilleme / otomatik karar", "Özel nitelikli veri"],
        ),
        expected_grounding=set(),
        articles=[35],  # GDPR m.35
        sections=["risk", "etki"],
        special_category=True,
        retention_placeholder=False,
    ),
    EvalCase(
        name="ihlal_bildirim",
        request=GenerateRequest(
            type="ihlal",
            fields={"tarih": "2026-06-10", "tur": "Yetkisiz erişim", "kisi": "~500", "devam": "Kontrol altında"},
            veriler=["Sağlık verisi", "TC Kimlik No"],
        ),
        expected_grounding={"Sağlık Bilgileri", "Kimlik"},
        articles=[12, 33],  # KVKK m.12/5, GDPR m.33
        sections=["ihlal", "72"],
        special_category=True,
        retention_placeholder=False,
    ),
]


def by_name(name: str) -> EvalCase:
    for c in GOLDEN:
        if c.name == name:
            return c
    raise KeyError(name)
