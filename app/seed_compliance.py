"""compliance_requirements seed yükleyici — idempotent (delete-all + insert).

REQUIREMENTS: 6698 sayılı KVKK ve ikincil mevzuattan türetilmiş standart uyum
kontrol listesi. İçerik kanun metni + Kurum rehberlerine dayanır (uydurma yok);
her kalemin madde atfı vardır. Avukat onayına tabi taslaktır — kurumsal duruma
göre "uygulanmaz" işaretlenebilir.

`source_type='auto'` kalemler, ilgili doküman üretildiğinde (`doc_generated:<tür>`)
otomatik "yapıldı" önerir; kullanıcı onaylar. Diğerleri elle işaretlenir.

Çalıştırma:  python -m app.seed_compliance  (ya da app.seed içinden)
Önkoşul: alembic upgrade head (0007 tablosu).
"""

from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from .db import get_sessionmaker
from .models import ComplianceRequirement

# Her kalem: {key, title, madde_ref, description, group, source_type, auto_signal, sort_order}
REQUIREMENTS: list[dict] = [
    # — Aydınlatma ve Şeffaflık (m.10) —
    {"key": "aydinlatma_metni", "title": "Aydınlatma metni hazırlandı ve ilgili kişilere sunuluyor",
     "madde_ref": "KVKK m.10", "group": "Aydınlatma ve Şeffaflık",
     "description": "Veri sorumlusunun kimliği, işleme amaçları, aktarım alıcıları, toplama yöntemi ve hukuki sebebi ile m.11 hakları, veri elde edilirken ilgili kişiye bildirilmelidir.",
     "source_type": "auto", "auto_signal": "doc_generated:aydinlatma", "sort_order": 10},
    {"key": "cerez_politikasi", "title": "Çerez politikası ve çerez aydınlatması yayımlandı",
     "madde_ref": "KVKK m.10 · Kurul Çerez Rehberi", "group": "Aydınlatma ve Şeffaflık",
     "description": "Web sitesi/uygulamada kullanılan çerezler için kategorilere ayrılmış çerez aydınlatması ve zorunlu olmayan çerezler için rıza yönetimi (onay bandı) bulunmalıdır.",
     "source_type": "auto", "auto_signal": "doc_generated:cerez", "sort_order": 20},
    {"key": "aydinlatma_kanallari", "title": "Aydınlatma tüm veri toplama kanallarında yapılıyor",
     "madde_ref": "KVKK m.10", "group": "Aydınlatma ve Şeffaflık",
     "description": "Form, sözleşme, çağrı merkezi, İK başvurusu, kamera vb. her veri toplama noktasında aydınlatma yükümlülüğü yerine getirilmelidir.",
     "source_type": "manual", "auto_signal": None, "sort_order": 30},

    # — Hukuki Sebep ve Rıza (m.5, m.6) —
    {"key": "hukuki_sebep_eslemesi", "title": "Her işleme faaliyeti bir hukuki sebebe bağlandı",
     "madde_ref": "KVKK m.5", "group": "Hukuki Sebep ve Rıza",
     "description": "İşlemeler m.5/2'deki sebeplere (sözleşme, hukuki yükümlülük, meşru menfaat vb.) dayandırılmalı; hiçbiri yoksa açık rıza alınmalıdır.",
     "source_type": "manual", "auto_signal": None, "sort_order": 40},
    {"key": "acik_riza_yonetimi", "title": "Açık rıza gerektiren işlemler için rıza alınıyor ve kayıtlanıyor",
     "madde_ref": "KVKK m.5/1, m.6/2", "group": "Hukuki Sebep ve Rıza",
     "description": "Açık rıza; belirli bir konuya ilişkin, bilgilendirmeye dayalı ve özgür iradeyle olmalı; geri alınabilmeli ve ispatı için kayıt altına alınmalıdır. Açık rıza bir hizmet şartına bağlanamaz.",
     "source_type": "manual", "auto_signal": None, "sort_order": 50},
    {"key": "ozel_nitelikli_veri", "title": "Özel nitelikli veriler için ek şartlar sağlanıyor",
     "madde_ref": "KVKK m.6", "group": "Hukuki Sebep ve Rıza",
     "description": "Sağlık, biyometrik, din, cinsel hayat vb. özel nitelikli veriler m.6'daki şartlarla işlenmeli; sağlık verileri için Kurul'un belirlediği yeterli önlemler alınmalıdır.",
     "source_type": "manual", "auto_signal": None, "sort_order": 60},

    # — Kayıt ve VERBİS (m.16) —
    {"key": "isleme_envanteri", "title": "Kişisel veri işleme envanteri hazırlandı ve güncel",
     "madde_ref": "KVKK m.16 · Yönetmelik m.5", "group": "Kayıt ve VERBİS",
     "description": "Süreç bazında kişi grubu, veri kategorisi, amaç, hukuki sebep, saklama süresi, alıcı ve aktarım bilgilerini içeren işleme envanteri tutulmalı ve güncel kalmalıdır.",
     "source_type": "auto", "auto_signal": "doc_generated:kayit", "sort_order": 70},
    {"key": "verbis_kaydi", "title": "VERBİS kaydı yapıldı (kayıt yükümlüsü isek)",
     "madde_ref": "KVKK m.16", "group": "Kayıt ve VERBİS",
     "description": "Kayıt yükümlülüğü kapsamındaki veri sorumluları Sicil'e kaydolmalı ve bildirimlerini güncel tutmalıdır. İstisna kapsamındaysak bu kalem 'uygulanmaz' işaretlenir.",
     "source_type": "manual", "auto_signal": None, "sort_order": 80},
    {"key": "veri_sorumlusu_temsilci", "title": "Veri sorumlusu / irtibat kişisi belirlendi",
     "madde_ref": "KVKK m.16 · Yönetmelik", "group": "Kayıt ve VERBİS",
     "description": "VERBİS'e kayıtlı veri sorumluları için irtibat kişisi atanmalı ve iletişim bilgileri güncel tutulmalıdır.",
     "source_type": "manual", "auto_signal": None, "sort_order": 90},

    # — Veri Güvenliği: İdari Tedbirler (m.12) —
    {"key": "kisisel_veri_politikasi", "title": "Kişisel veri işleme ve koruma politikası yürürlükte",
     "madde_ref": "KVKK m.12", "group": "Veri Güvenliği — İdari",
     "description": "Kurumsal kişisel veri işleme, saklama-imha ve güvenlik politikaları yazılı olmalı, yönetimce onaylanmalı ve çalışanlara duyurulmalıdır.",
     "source_type": "manual", "auto_signal": None, "sort_order": 100},
    {"key": "calisan_farkindalik", "title": "Çalışanlara KVKK farkındalık eğitimi verildi",
     "madde_ref": "KVKK m.12 · Kurul Rehberi", "group": "Veri Güvenliği — İdari",
     "description": "Kişisel veriye erişen personel için düzenli farkındalık/eğitim yapılmalı ve kayıt altına alınmalıdır.",
     "source_type": "manual", "auto_signal": None, "sort_order": 110},
    {"key": "gizlilik_taahhutnameleri", "title": "Personel gizlilik taahhütnameleri imzalandı",
     "madde_ref": "KVKK m.12", "group": "Veri Güvenliği — İdari",
     "description": "Kişisel veriye erişen çalışanlarla gizlilik/veri güvenliği taahhütnameleri imzalanmalı; yetki kapsamı tanımlanmalıdır.",
     "source_type": "manual", "auto_signal": None, "sort_order": 120},
    {"key": "erisim_yetki_matrisi", "title": "Erişim yetkileri 'bilmesi gereken' ilkesine göre tanımlı",
     "madde_ref": "KVKK m.12 · Kurul Teknik-İdari Tedbirler Rehberi", "group": "Veri Güvenliği — İdari",
     "description": "Kişisel verilere erişim rol bazlı olmalı, yetkiler periyodik gözden geçirilmeli ve ayrılan personelin erişimi derhal kaldırılmalıdır.",
     "source_type": "manual", "auto_signal": None, "sort_order": 130},

    # — Veri Güvenliği: Teknik Tedbirler (m.12) —
    {"key": "yetkilendirme_kimlik_dogrulama", "title": "Yetkilendirme ve güçlü kimlik doğrulama uygulanıyor",
     "madde_ref": "KVKK m.12", "group": "Veri Güvenliği — Teknik",
     "description": "Sistemlere erişimde güçlü parola politikası ve mümkün olduğunda çok faktörlü kimlik doğrulama kullanılmalıdır.",
     "source_type": "manual", "auto_signal": None, "sort_order": 140},
    {"key": "sifreleme", "title": "Kritik veriler aktarım ve saklamada şifreleniyor",
     "madde_ref": "KVKK m.12 · Kurul Teknik-İdari Tedbirler Rehberi", "group": "Veri Güvenliği — Teknik",
     "description": "Özel nitelikli ve kritik kişisel veriler iletimde (TLS) ve saklamada şifrelenmeli; anahtar yönetimi güvenli yapılmalıdır.",
     "source_type": "manual", "auto_signal": None, "sort_order": 150},
    {"key": "log_kayitlari", "title": "Erişim ve işlem log kayıtları tutuluyor",
     "madde_ref": "KVKK m.12", "group": "Veri Güvenliği — Teknik",
     "description": "Kişisel veriye erişim ve kritik işlemler için izlenebilir, değiştirilemez log kayıtları tutulmalı ve makul süre saklanmalıdır.",
     "source_type": "manual", "auto_signal": None, "sort_order": 160},
    {"key": "yedekleme", "title": "Düzenli yedekleme ve geri yükleme testi yapılıyor",
     "madde_ref": "KVKK m.12", "group": "Veri Güvenliği — Teknik",
     "description": "Veri kaybına karşı düzenli yedek alınmalı, yedekler güvenli ortamda tutulmalı ve geri yükleme periyodik test edilmelidir.",
     "source_type": "manual", "auto_signal": None, "sort_order": 170},
    {"key": "guvenlik_guncellemeleri", "title": "Sistemler güncel ve sızma/zafiyet testleri yapılıyor",
     "madde_ref": "KVKK m.12 · Kurul Teknik-İdari Tedbirler Rehberi", "group": "Veri Güvenliği — Teknik",
     "description": "Yazılım/sistem güncellemeleri düzenli uygulanmalı, güncel anti-virüs/güvenlik duvarı bulunmalı ve periyodik zafiyet taraması yapılmalıdır.",
     "source_type": "manual", "auto_signal": None, "sort_order": 180},

    # — İlgili Kişi Hakları (m.11, m.13) —
    {"key": "basvuru_sureci", "title": "İlgili kişi başvuru süreci tanımlı (30 gün)",
     "madde_ref": "KVKK m.13 · Başvuru Tebliği", "group": "İlgili Kişi Hakları",
     "description": "İlgili kişi başvuruları için başvuru kanalı, kimlik doğrulama ve en geç 30 gün içinde ücretsiz (istisnalar hariç) yanıtlama süreci kurulmalıdır.",
     "source_type": "manual", "auto_signal": None, "sort_order": 190},
    {"key": "haklar_karsilanmasi", "title": "m.11 hakları (erişim, düzeltme, silme) işletilebiliyor",
     "madde_ref": "KVKK m.11", "group": "İlgili Kişi Hakları",
     "description": "İlgili kişinin bilgi talebi, düzeltme, silme/yok etme ve itiraz haklarını karşılayacak teknik/idari süreçler bulunmalıdır.",
     "source_type": "manual", "auto_signal": None, "sort_order": 200},

    # — Saklama ve İmha (m.7) —
    {"key": "saklama_imha_politikasi", "title": "Saklama ve imha politikası hazırlandı",
     "madde_ref": "KVKK m.7 · Silme-Yok Etme Yönetmeliği", "group": "Saklama ve İmha",
     "description": "Kayıt yükümlüleri için saklama ve imha politikası hazırlanmalı; her veri kategorisi için saklama süresi ve imha yöntemi belirlenmelidir.",
     "source_type": "manual", "auto_signal": None, "sort_order": 210},
    {"key": "periyodik_imha", "title": "Süresi dolan veriler periyodik olarak imha ediliyor",
     "madde_ref": "KVKK m.7 · Yönetmelik m.11", "group": "Saklama ve İmha",
     "description": "Saklama süresi dolan kişisel veriler silme, yok etme veya anonim hale getirme yoluyla periyodik imha (en fazla 6 aylık periyot) ile ortadan kaldırılmalıdır.",
     "source_type": "manual", "auto_signal": None, "sort_order": 220},

    # — Aktarım ve Sözleşmeler (m.8, m.9) —
    {"key": "veri_isleyen_sozlesmeleri", "title": "Veri işleyenlerle KVKK sözleşmeleri imzalandı",
     "madde_ref": "KVKK m.12/2", "group": "Aktarım ve Sözleşmeler",
     "description": "Tedarikçi/veri işleyenlerle güvenlik yükümlülüklerini içeren yazılı sözleşme (DPA) yapılmalı; veri işleyen sorumlulukla müştereken yükümlüdür.",
     "source_type": "auto", "auto_signal": "doc_generated:dpa", "sort_order": 230},
    {"key": "yurtdisi_aktarim", "title": "Yurt dışı aktarımlar mevzuata uygun yapılıyor",
     "madde_ref": "KVKK m.9", "group": "Aktarım ve Sözleşmeler",
     "description": "Yurt dışına aktarımda uygun güvence (yeterlilik kararı, standart sözleşme/bağlayıcı kurallar veya açık rıza) sağlanmalı ve gerekli bildirimler yapılmalıdır. Yurt dışı aktarım yoksa 'uygulanmaz'.",
     "source_type": "manual", "auto_signal": None, "sort_order": 240},
    {"key": "dpia", "title": "Yüksek riskli işlemler için etki değerlendirmesi yapıldı",
     "madde_ref": "Kurul Rehberi (DPIA)", "group": "Aktarım ve Sözleşmeler",
     "description": "Yeni teknoloji, profilleme veya büyük ölçekli özel nitelikli veri işleme gibi yüksek riskli faaliyetlerde veri koruma etki değerlendirmesi önerilir.",
     "source_type": "auto", "auto_signal": "doc_generated:dpia", "sort_order": 250},

    # — İhlal Yönetimi (m.12/5) —
    {"key": "ihlal_mudahale_plani", "title": "Veri ihlali müdahale planı hazır",
     "madde_ref": "KVKK m.12/5", "group": "İhlal Yönetimi",
     "description": "İhlal tespiti, değerlendirme, kayıt ve bildirim adımlarını içeren yazılı müdahale planı bulunmalı; sorumlular ve iletişim zinciri tanımlı olmalıdır.",
     "source_type": "auto", "auto_signal": "doc_generated:ihlal", "sort_order": 260},
    {"key": "ihlal_bildirim_72saat", "title": "İhlalde 72 saat içinde Kurul'a bildirim süreci var",
     "madde_ref": "KVKK m.12/5 · Kurul Kararı", "group": "İhlal Yönetimi",
     "description": "Veri ihlali öğrenildiğinde en kısa sürede ve en geç 72 saat içinde Kurul'a, etkilenen ilgili kişilere ise makul sürede bildirim yapılmalıdır.",
     "source_type": "manual", "auto_signal": None, "sort_order": 270},
]


def seed_compliance_requirements(session: Session, requirements: list[dict]) -> int:
    """Gereksinim referans tablosunu idempotent yükler: tümünü sil + yeniden ekle.

    Global referans veri (tenant'a bağlı değil); delete+insert drift'siz ve basit.
    Yüklenen satır sayısını döndürür.
    """
    session.execute(delete(ComplianceRequirement))
    session.add_all([ComplianceRequirement(**r) for r in requirements])
    session.flush()
    return len(requirements)


def main() -> None:
    sm = get_sessionmaker()
    with sm() as session:
        n = seed_compliance_requirements(session, REQUIREMENTS)
        session.commit()
        print(f"{n} uyum gereksinimi yüklendi.")


if __name__ == "__main__":
    main()
