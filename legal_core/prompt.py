"""Prompt kurulumu — envanter + iş kuralları + kullanıcı girdisini birleştirir.

worker.py'nin prompt mantığı buraya saf olarak taşındı. DISCLAIMER emoji'sizdir
(web kopyasıyla tutarlı). build_prompt yalnızca string üretir; model çağrısı yapmaz.
"""

from __future__ import annotations

import json

from .aggregate_sections import Section, _merge_dedup
from .models import ClientProfile, InventoryRecord, ProcessRecord

# Bir bolum alani (ornegin saklama suresi) envanterde bulunamadigi durumda
# koşulsuz basilan yer tutucu (spec: hicbir m.10 basligi sessizce dusmemeli).
ONAY_BEKLEYEN_PLACEHOLDER = "[Avukat tarafından doldurulacak]"

# Her çıktının en altına eklenen zorunlu uyarı (hooks.json playbook'u ile uyumlu).
DISCLAIMER = (
    "Bu çıktı avukat incelemesine tabi hukuki taslaktır. Hukuki tavsiye niteliği "
    "taşımaz. Her karar ve resmi belge, konuya hâkim bir hukukçu tarafından "
    "incelenmeli ve onaylanmalıdır."
)

# Disclaimer'ın yeniden eklenip eklenmeyeceğini saptamak için sabit anahtar ifade.
DISCLAIMER_MARKER = "avukat incelemesine tabi"

# format_processes'in varsayılan kırpma tavanı (build_prompt ile paylaşılır).
DEFAULT_PROCESS_CAP = 60

# Tedbir bloğunun basılacağı doküman türleri (tedbirler bölümü olanlar).
MEASURE_DOC_TYPES = frozenset({"kayit", "dpia", "ihlal"})


def format_inventory(records: list[InventoryRecord]) -> str:
    """Envanter kayıtlarını prompt'a gömülecek bağlayıcı metne dönüştürür."""
    if not records:
        return (
            "(Seçilen etiketler için envanterde eşleşen kayıt bulunamadı. Bu durumda "
            "hukuki sebep/amaç/süre için somut bir dayanak yoktur — bunları UYDURMA, "
            "ilgili alanları '[Avukat tarafından doldurulacak]' olarak bırak.)\n"
        )
    out = ""
    for r in records:
        out += f"\n### Kategori: {r.kategori}\n"
        if r.veri_turleri:
            out += f"- Veri türleri: {', '.join(r.veri_turleri[:25])}\n"
        if r.amaclar:
            out += f"- İşleme amaçları: {', '.join(r.amaclar)}\n"
        if r.hukuki_sebepler:
            out += f"- Hukuki sebepler: {', '.join(r.hukuki_sebepler)}\n"
        if r.kisi_gruplari:
            out += f"- İlgili kişi grupları: {', '.join(r.kisi_gruplari[:15])}\n"
        sure = r.saklama_sureleri
        out += (
            "- Saklama süreleri: "
            f"{', '.join(sure) if sure else '[envanterde belirtilmemiş — UYDURMA]'}\n"
        )
    return out


def format_processes(records: list[ProcessRecord], cap: int = DEFAULT_PROCESS_CAP) -> str:
    """Süreçleri prompt bloklarına çevirir — her süreç KENDİ hukuki sebebi + saklamasıyla.

    Kategori ekseninde tüm süreçlerin süreleri tek listeye yığıldığı için model hangi
    sürenin hangi sürece ait olduğunu seçemiyordu (spec §1); bu format o bağlamı korur.
    Cap aşılırsa kırpma SESSİZ OLMAZ — prompt'a açık not düşülür.
    """
    if not records:
        return ""
    total = len(records)
    shown = records[:cap] if cap and total > cap else records
    out = ""
    for r in shown:
        out += f"\n### Süreç: {r.departman} / {r.is_sureci} / {r.alt_surec}\n"
        out += f"- Kişi grubu: {r.kisi_grubu}\n"
        if r.kategoriler:
            out += f"- Kategoriler: {', '.join(r.kategoriler)}\n"
        if r.veri_turleri:
            out += f"- Veri türleri: {', '.join(r.veri_turleri[:25])}\n"
        if r.amaclar:
            out += f"- Amaçlar: {', '.join(r.amaclar)}\n"
        if r.hukuki_sebepler:
            out += f"- Hukuki sebep: {', '.join(r.hukuki_sebepler)}\n"
        if r.dayanaklar:
            out += f"- Dayanak: {', '.join(r.dayanaklar)}\n"
        out += (
            "- Saklama: "
            f"{', '.join(r.saklama_sureleri) if r.saklama_sureleri else '[envanterde belirtilmemiş — UYDURMA]'}\n"
        )
        if r.aktarim:
            out += f"- Alıcı/Aktarım: {', '.join(r.aktarim)}\n"
        if r.islem:
            out += f"- İşlem: {', '.join(r.islem)}\n"
        if r.konum:
            out += f"- Konum: {', '.join(r.konum)}\n"
        if r.idari_tedbirler:
            out += f"- İdari tedbir: {', '.join(r.idari_tedbirler)}\n"
        if r.teknik_tedbirler:
            out += f"- Teknik tedbir: {', '.join(r.teknik_tedbirler)}\n"
    if cap and total > cap:
        out += f"\n(NOT: {total} süreçten ilk {cap} tanesi gösteriliyor — liste kırpıldı.)\n"
    return out


def format_measures(measures: list[str]) -> str:
    """Global tedbirleri prompt bloğuna çevirir. Boşsa boş string."""
    if not measures:
        return ""
    out = "\n"
    for m in measures:
        out += f"- {m}\n"
    return out


def build_prompt(
    doc_type: str,
    user_input: dict,
    inventory: list[InventoryRecord],
    rules: list[str],
    processes: list[ProcessRecord] | None = None,
    process_cap: int = DEFAULT_PROCESS_CAP,
    measures: list[str] | None = None,
) -> str:
    """Tam üretim prompt'unu kurar (model-agnostik).

    Süreç kayıtları verilirse ONLAR birincil bağlayıcı çerçevedir (her süreç kendi hukuki
    sebebi + saklamasıyla); kategori envanteri tamamlayıcı sözlük olarak kalır.
    """
    kurallar_metni = "## KVKK ENVANTERİ — BAĞLAYICI KAYITLAR\n" + format_inventory(inventory)

    surec_metni = ""
    if processes:
        surec_metni = (
            "## SÜREÇ ENVANTERİ — BAĞLAYICI (her süreç KENDİ hukuki sebebi ve saklama süresiyle;\n"
            "başka bir sürecin süresini bu sürece UYGULAMA)\n"
            + format_processes(processes, cap=process_cap)
            + "\n"
        )

    tedbir_metni = ""
    if measures and doc_type in MEASURE_DOC_TYPES:
        tedbir_metni = (
            "## TEKNİK VE İDARİ TEDBİRLER (KVKK m.12 — org geneli standart liste; "
            "belgenin tedbirler bölümünde bunları kullan, UYDURMA)\n"
            + format_measures(measures)
            + "\n"
        )

    is_mantigi = "## BAĞLAYICI İŞ KURALLARI (HARFİYEN UY)\n"
    for i, br in enumerate(rules, 1):
        is_mantigi += f"{i}. {br}\n"

    return f"""Sen KVKK (6698) ve GDPR (2016/679) uzmanı bir hukuk asistanısın.
Kullanıcı '{doc_type}' türünde bir doküman istiyor. Aşağıdaki BAĞLAYICI çerçevenin
dışına çıkma; kendi kafandan hukuki prosedür, dayanak, süre veya şablon uydurma.

{is_mantigi}
{surec_metni}{tedbir_metni}
{kurallar_metni}

## KULLANICI GİRDİLERİ
{json.dumps(user_input, ensure_ascii=False, indent=2)}

Yukarıdaki envanter kayıtlarına ve iş kurallarına KESİNLİKLE bağlı kalarak, eksiksiz
ve Markdown formatında bir doküman üret. Belgenin EN ALTINA aşağıdaki uyarıyı aynen ekle:

{DISCLAIMER}
"""


def ensure_disclaimer(text: str) -> str:
    """Model disclaimer'ı eklemeyi atladıysa kod düzeyinde garanti eder."""
    if DISCLAIMER_MARKER in text:
        return text
    return text.rstrip() + "\n\n---\n" + DISCLAIMER


def _field_or_placeholder(values: list[str]) -> str:
    """Dolu ise virgullu birlestirir; bossa KOŞULSUZ placeholder doner (asla atlanmaz)."""
    return ", ".join(values) if values else ONAY_BEKLEYEN_PLACEHOLDER


def _profile_line(label: str, value: str | None) -> str:
    return f"- {label}: {value if value else ONAY_BEKLEYEN_PLACEHOLDER}\n"


def _format_client_profile(profile: ClientProfile) -> str:
    out = _profile_line("Ad/Unvan", profile.ad)
    out += _profile_line("Unvan", profile.unvan)
    out += _profile_line("Adres", profile.adres)
    out += _profile_line("MERSİS No", profile.mersis)
    out += _profile_line("Vergi Dairesi", profile.vergi_dairesi)
    out += _profile_line("Vergi No", profile.vergi_no)
    out += _profile_line("KEP Adresi", profile.kep)
    out += _profile_line("E-posta", profile.eposta)
    out += _profile_line("Telefon", profile.telefon)
    return out


def _derive_kaynaklar(sections: list[Section], boilerplate: dict) -> str:
    """Belge-düzeyi Veri Toplama Kaynakları'nı müvekkil envanterinden türetir.

    Avukat: kaynaklar müvekkile göre değişir. Bölümlerin toplama değerlerinin birleşimini
    liste yapar; hiçbir bölümde toplama yoksa sabit boilerplate'e düşer (uydurma yok).
    """
    toplama = _merge_dedup(*(s.toplama for s in sections))
    if not toplama:
        return boilerplate["kaynaklar"]
    return "\n".join(f"- {t}" for t in toplama)


def _format_aydinlatma_section(section: Section) -> str:
    kisi_gruplari = ", ".join(section.kisi_gruplari) if section.kisi_gruplari else ONAY_BEKLEYEN_PLACEHOLDER
    veriler = _field_or_placeholder(section.kategoriler + section.veri_turleri)
    return f"""
### {section.is_sureci}
(İlgili kişi grupları: {kisi_gruplari})
- İşlenen kişisel veriler: {veriler}
- İşleme amaçları: {_field_or_placeholder(section.amaclar)}
- Hukuki sebep: {_field_or_placeholder(section.hukuki_sebepler)}
- Saklama süresi: {_field_or_placeholder(section.saklama_sureleri)}
- Aktarım: {_field_or_placeholder(section.aktarim)}
- Toplama yöntemi: {_field_or_placeholder(section.toplama)}
"""


def build_aydinlatma_envanter_prompt(
    sections: list[Section], boilerplate: dict, profile: ClientProfile,
) -> str:
    """Onaylı envanter bölümlerinden KVKK m.10 Aydınlatma Metni prompt'unu kurar.

    Mevcut build_prompt'tan farkı: her iş süreci bölümünde m.10'un ALTI başlığı
    KOŞULSUZ basılır (boşsa placeholder) — sahada gözlenen sessiz düşme hatasının
    çözümü budur (bkz. dosya başlığı brief).
    """
    if sections:
        surecler_metni = "".join(_format_aydinlatma_section(s) for s in sections)
    else:
        surecler_metni = (
            "\n(UYARI: Seçilen hedef gruplar için envanterde iş süreci bulunamadı — "
            "aşağıda örnek bir bölüm İSKELET olarak yer almaz; bu durumu belgede "
            f"açıkça belirt ve ilgili alanları {ONAY_BEKLEYEN_PLACEHOLDER} olarak bırak.)\n"
        )

    return f"""Sen KVKK (6698) uzmanı hukuk asistanısın. Aşağıdaki yapılandırılmış envanter
bölümlerinden KVKK m.10 kapsamında tek bir Aydınlatma Metni üret.

Yalnız aşağıda verilen değerleri kullan; hukuki sebep, saklama süresi, amaç veya
aktarım UYDURMA.

Her iş süreci bölümünde şu ALTI başlığın HEPSİ eksiksiz yer alacak: İşlenen kişisel
veriler, İşleme amaçları, Hukuki sebep, Saklama süresi, Aktarım, Toplama yöntemi.
Hiçbirini atlama, sırasını koru.

Bir başlığın değeri "{ONAY_BEKLEYEN_PLACEHOLDER}" ise onu AYNEN o şekilde yaz; boş
bırakma, uydurma, atlama.

Hukuki sebep değerlerindeki KVKK madde atıflarını (ör. m.5/2, m.6, açık rıza)
OLDUĞU GİBİ koru; yeni madde numarası ekleme/uydurma.

Bir bölümün Aktarım değeri "{ONAY_BEKLEYEN_PLACEHOLDER}" ise, o bölümde aktarımı boş
bırakma: aşağıdaki STANDART AKTARIM HÜKÜMLERİ'ni o bölüme uyarla. Envanterde bölüme
özgü bir alıcı verilmişse onu bu standart hükümlerle birlikte belirt; yeni alıcı uydurma.

Saklama süresini AÇIKÇA yaz (süre değerlerini aynen koru) ve saklamanın "Saklama ve
Arşiv Faaliyetlerinin Yürütülmesi" amacı kapsamında yapıldığını ifade et. Saklama süresi
değeri "{ONAY_BEKLEYEN_PLACEHOLDER}" ise süreyi uydurma; yalnız bu çerçeveyi belirt.

Her işleme amacını, o bölümde verilen hukuki sebeplerden EN UYGUN olanı ile eşleştir ve
amacın yanında parantez içinde bu eşleştirmenin kısa gerekçesini belirt (ör. "... amacı
(m.5/2-c — sözleşmenin ifası için zorunlu olduğundan)"). Yalnız o bölümde verilen hukuki
sebepleri kullan; envanterde bulunmayan yeni bir hukuki sebep ekleme/uydurma. Bölümün
hukuki sebebi "{ONAY_BEKLEYEN_PLACEHOLDER}" ise eşleştirme yapma, gerekçe uydurma.

## VERİ SORUMLUSU KİMLİĞİ
{_format_client_profile(profile)}

## STANDART BÖLÜMLER (AYNEN KULLAN, DEĞİŞTİRME)

### Tanımlar
{boilerplate["tanimlar"]}

### Veri Toplama Kaynakları
{_derive_kaynaklar(sections, boilerplate)}

### Ortak Hükümler
{boilerplate["ortak_hukumler"]}

### Standart Aktarım Hükümleri
{boilerplate["aktarim_standart"]}

## İŞ SÜREÇLERİ BÖLÜMLERİ
{surecler_metni}

## İLGİLİ KİŞİNİN HAKLARI (m.11)
{boilerplate["haklar_m11"]}

## BAŞVURU USULÜ
{boilerplate["basvuru_usulu"]}

Yukarıdaki bilgilere KESİNLİKLE bağlı kalarak eksiksiz ve Markdown formatında bir
Aydınlatma Metni üret. Belgenin EN ALTINA aşağıdaki uyarıyı aynen ekle:

{DISCLAIMER}
"""


def build_kayit_envanter_prompt(
    records: list[ProcessRecord], profile: ClientProfile, measures: list[str], rules: list[str],
) -> str:
    """Müvekkil envanterinden VERBİS/RoPA işleme kaydı prompt'u kurar (aydinlatma envanter-modu deseni)."""
    surecler = format_processes(records) if records else "\n(Envanterde süreç yok — üretilecek işleme faaliyeti yok.)\n"
    tedbir = format_measures(measures)
    kurallar = ""
    for i, r in enumerate(rules, 1):
        kurallar += f"{i}. {r}\n"

    return f"""Sen KVKK (6698) m.16 ve GDPR m.30 uzmanı bir hukuk asistanısın. Aşağıdaki müvekkil
kimliği ve işleme envanterinden (VERBİS/RoPA) bir Kişisel Veri İşleme Kaydı üret.

Yalnız aşağıda verilen envanter değerlerini kullan; hukuki sebep, saklama süresi, amaç, alıcı veya
aktarım UYDURMA. Envanterde boş olan bir zorunlu alanı "{ONAY_BEKLEYEN_PLACEHOLDER}" olarak bırak.

Her işleme faaliyetini (süreç) VERBİS sütun mantığıyla ele al: İş Süreci · Veri Konusu Kişi Grubu ·
Kişisel Veri Kategorisi/Türü · İşleme Amaçları · Hukuki Sebep · Saklama Süresi · Alıcı/Aktarım ·
Teknik ve İdari Tedbirler. Her sürecin KENDİ hukuki sebebini ve saklama süresini kullan; başka bir
sürecin değerini bu sürece UYGULAMA.

## VERİ SORUMLUSU KİMLİĞİ
{_format_client_profile(profile)}

## İŞLEME ENVANTERİ — BAĞLAYICI SÜREÇLER
{surecler}

## TEKNİK VE İDARİ TEDBİRLER (org geneli standart liste; bunları kullan, UYDURMA)
{tedbir}

## BAĞLAYICI İŞ KURALLARI (HARFİYEN UY)
{kurallar}
Yukarıdaki bilgilere KESİNLİKLE bağlı kalarak eksiksiz ve Markdown formatında bir İşleme Kaydı üret.
Belgenin EN ALTINA aşağıdaki uyarıyı aynen ekle:

{DISCLAIMER}
"""
