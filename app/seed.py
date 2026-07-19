"""Grounding referans verisini Postgres'e yükler (idempotent).

- categories.json -> categories tablosu (anahtarlar NFC normalize).
- 21 hukuki iş kuralı -> business_rules tablosu.

Çalıştırma:  python -m app.seed
Migration'lar uygulandıktan sonra çağrılmalıdır (alembic upgrade head).
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from sqlalchemy import delete

from .db import get_sessionmaker
from .models import BusinessRule, Category, Process

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CATEGORIES_PATH = DATA_DIR / "categories.json"
PROCESSES_PATH = DATA_DIR / "processes.json"

# (dokuman_turu, kural_metni) — seed_rules.py (Electron) ile birebir.
RULES: list[tuple[str, str]] = [
    ("Tümü", "Her hukuki değerlendirmede ilgili KVKK/GDPR maddesine doğrudan atıf yap "
             "(ör. KVKK m.5/2-ç, GDPR m.6/1-c). Atıfsız hukuki ifade kullanma."),
    ("Tümü", "Risk değerlendirmesi içeren bölümlerde 4'lü matris kullan: "
             "Kritik / Yüksek / Orta / Düşük."),
    ("aydinlatma", "Aydınlatma metni KVKK m.10 ve GDPR m.13-14 zorunlu unsurlarını içermeli: "
                   "veri sorumlusu kimliği, işleme amaçları, hukuki sebep, aktarılan alıcı "
                   "grupları, toplama yöntemi ve hukuki sebebi, ilgili kişi hakları (m.11)."),
    ("aydinlatma", "Her kişisel veri kategorisi için işleme amacını ve hukuki dayanağını "
                   "AYRI AYRI, tablo formatında belirt (GDPR m.6 / KVKK m.5)."),
    ("aydinlatma", "İlgili kişinin KVKK m.11 haklarını ve başvuru yolunu (önce veri "
                   "sorumlusuna başvuru, ardından Kurul'a şikayet) mutlaka ekle."),
    ("cerez", "Çerezleri kategori bazında tablola: Zorunlu / Fonksiyonel / Analitik / "
              "Pazarlama. Sütunlar: Kategori | Amaç | Hukuki Dayanak | Saklama Süresi | "
              "Örnek çerezler."),
    ("cerez", "Zorunlu olmayan çerezler için önceden AÇIK RIZA (opt-in) ve bir tercih "
              "yönetim mekanizması (CMP) gerektiğini açıkça belirt."),
    ("kayit", "Kayıt, GDPR m.30 ve VERBİS unsurlarını içermeli: işleme amaçları, veri "
              "kategorileri, ilgili kişi grupları, alıcı kategorileri, yurt dışı aktarım, "
              "saklama süreleri, teknik ve idari tedbirler."),
    ("kayit", "Her kategori için somut saklama süresi gerekir (GDPR m.13/2-a). Envanterde "
              "süre yoksa UYDURMA; alanı boş bırakıp '[Avukat tarafından belirlenecek]' yaz."),
    ("dpa", "DPA zorunlu unsurları: işleme konusu/süresi/amacı, veri kategorileri, yalnızca "
            "belgelenmiş talimatla işleme, gizlilik taahhüdü, m.32 tedbirleri, alt işleyici "
            "onay prosedürü, ihlal bildirim süresi, sözleşme sonu silme/iade, denetim hakkı."),
    ("dpa", "KIRMIZI BAYRAK: İşleyicinin kişisel veriyi kendi ticari amaçları için "
            "kullanmasına izin veren madde → 'Kabul edilemez'."),
    ("dpa", "KIRMIZI BAYRAK: Veri ihlali bildirim süresi 72 saati aşıyorsa → 'Reddedilmeli'."),
    ("dpa", "KIRMIZI BAYRAK: Sözleşme sonunda silme/iade yerine süresiz saklamayı ima eden "
            "boşluk → 'Reddedilmeli'."),
    ("dpa", "Yurt dışı transfer varsa SCCs (2021 AB SSM) / KVKK m.9 taahhütnamesi / Kurul "
            "kararı referansı ara; 'uygun ülkelere aktarım' gibi muğlak ifadeleri işaretle."),
    ("dpia", "DPIA zorunluluk testi: profilleme ile otomatik karar, özel nitelikli veri, "
             "büyük ölçekli kamu alanı izleme, yeni teknoloji (YZ/IoT/biyometri), savunmasız "
             "grup, veri eşleştirme kriterlerinden 2 veya daha fazlası varsa DPIA ZORUNLU."),
    ("dpia", "DPIA katı 8 bölüm içermeli: 1) Proje ve Kapsam 2) İşlemenin Tanımı 3) Veri Akış "
             "Haritası 4) Uyum Değerlendirmesi 5) Risk Matrisi 6) Risk Azaltma Tedbirleri "
             "7) Sonuç Kararı 8) Güncelleme Takvimi."),
    ("dpia", "Risk skoru = Olasılık (1-5) × Etki (1-5). Skor: 1-4 Düşük, 5-9 Orta, "
             "10-14 Yüksek, 15-25 Kritik."),
    ("dpia", "Sonuç kararı şu seçeneklerden olmalı: DEVAM / KOŞULLU DEVAM / KURUL DANIŞMASI "
             "GEREKLİ (GDPR m.36) / DURDUR. Yüksek risk azaltılamıyorsa Kurul danışması belirt."),
    ("ihlal", "İhlal bildirimi KVKK Kurulu'na ve GDPR DPA'ya en geç 72 SAAT içinde yapılır "
              "(GDPR m.33). Form: ihlalin niteliği, etkilenen veri kategorileri ve tahmini "
              "kişi sayısı, olası sonuçlar, alınan/alınacak tedbirler."),
    ("ihlal", "İhlal yüksek risk taşıyorsa ilgili kişilere de bildirim (GDPR m.34) "
              "gerektiğini değerlendir ve belirt."),
    ("ihlal", "Bildirim 72 saati aştıysa gecikmenin gerekçesi zorunludur — bunu forma ekle."),
]


def seed() -> None:
    raw = json.loads(CATEGORIES_PATH.read_text(encoding="utf-8"))
    categories = {unicodedata.normalize("NFC", k): v for k, v in raw.items()}
    processes = json.loads(PROCESSES_PATH.read_text(encoding="utf-8"))

    session = get_sessionmaker()()
    try:
        # Idempotent: temizle + yeniden yükle.
        session.execute(delete(Category))
        session.execute(delete(BusinessRule))
        session.execute(delete(Process))
        session.add_all(Category(name=name, data=data) for name, data in categories.items())
        session.add_all(BusinessRule(dokuman_turu=t, kural_metni=m) for t, m in RULES)
        session.add_all(
            Process(sector=p["sector"], kisi_grubu=p["kisi_grubu"], departman=p["departman"],
                    is_sureci=p["is_sureci"], alt_surec=p["alt_surec"], data=p["data"])
            for p in processes
        )
        session.commit()
        print(f"Seed tamam: {len(categories)} kategori, {len(RULES)} iş kuralı, {len(processes)} süreç.")
    finally:
        session.close()


if __name__ == "__main__":
    seed()
