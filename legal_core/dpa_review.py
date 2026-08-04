"""DPA-İncele: kanonik KVKK m.12 kontrol listesi + review veri modelleri — saf.

(Task 3 bu dosyaya prompt-güdümlü JSON analiz fonksiyonlarını ekler.)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewItem:
    id: str
    baslik: str
    kvkk_ref: str
    aranan: str
    kirmizi_bayrak: bool = False


@dataclass(frozen=True)
class ReviewFinding:
    madde_id: str
    durum: str
    alinti: str
    gerekce: str
    oneri: str


@dataclass(frozen=True)
class DpaReviewResult:
    bulgular: list[ReviewFinding]
    uygun: int
    eksik: int
    yetersiz: int
    kirmizi_bayrak: int
    disclaimer: str


@dataclass(frozen=True)
class ReviewContext:
    veri_sorumlusu: str
    isleyen_adi: str | None
    yurt_disi: bool
    aktarim_adlari: list[str]
    kategoriler: list[str]


DPA_CHECKLIST: list[ReviewItem] = [
    ReviewItem("belgeli_talimat", "Belgelenmiş talimatla işleme",
               "KVKK m.12", "İşleyen kişisel veriyi yalnız veri sorumlusunun yazılı/belgelenmiş talimatıyla işler."),
    ReviewItem("konu_kapsam", "İşleme konusu, süresi, amacı ve veri kategorileri",
               "KVKK m.12", "Sözleşme işlemenin konusunu, süresini, amacını ve kapsanan veri kategorilerini tanımlar."),
    ReviewItem("gizlilik", "Gizlilik taahhüdü",
               "KVKK m.12/3", "İşleyen ve çalışanları için süresiz gizlilik/sır saklama yükümlülüğü."),
    ReviewItem("tedbirler", "Teknik ve idari tedbirler",
               "KVKK m.12/1", "İşleyen uygun güvenlik düzeyini sağlayacak teknik ve idari tedbirleri taahhüt eder."),
    ReviewItem("alt_isleyen", "Alt-işleyen onay prosedürü",
               "KVKK m.12", "Alt-işleyen kullanımı veri sorumlusunun önceden yazılı iznine bağlıdır."),
    ReviewItem("ihlal_bildirim", "Veri ihlali bildirim yükümlülüğü ve süresi",
               "KVKK m.12/5", "İhlal en kısa sürede (≤72 saat) veri sorumlusuna bildirilir.", kirmizi_bayrak=True),
    ReviewItem("sozlesme_sonu", "Sözleşme sonunda silme/iade",
               "KVKK m.12", "Sözleşme bitiminde veriler veri sorumlusuna iade veya güvenli imha edilir.", kirmizi_bayrak=True),
    ReviewItem("denetim", "Denetim hakkı",
               "KVKK m.12", "Veri sorumlusuna denetim/uyum doğrulama hakkı tanınır."),
    ReviewItem("yurt_disi", "Yurt dışı aktarım güvenceleri",
               "KVKK m.9", "Yurt dışı aktarım varsa taahhütname/SCC/Kurul kararı referansı bulunur; muğlak ifade yok."),
    ReviewItem("kendi_amaci", "İşleyenin veriyi kendi amacı için kullanmaması",
               "KVKK m.12", "İşleyenin kişisel veriyi kendi ticari amaçları için kullanmasına izin YOKTUR.", kirmizi_bayrak=True),
    ReviewItem("ilgili_kisi", "İlgili kişi haklarına destek",
               "KVKK m.11", "İşleyen, ilgili kişi başvurularının karşılanmasında veri sorumlusuna yardımcı olur."),
]
