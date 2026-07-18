"""Prompt kurulumu — envanter + iş kuralları + kullanıcı girdisini birleştirir.

worker.py'nin prompt mantığı buraya saf olarak taşındı. DISCLAIMER emoji'sizdir
(web kopyasıyla tutarlı). build_prompt yalnızca string üretir; model çağrısı yapmaz.
"""

from __future__ import annotations

import json

from .models import InventoryRecord, ProcessRecord

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


def build_prompt(
    doc_type: str,
    user_input: dict,
    inventory: list[InventoryRecord],
    rules: list[str],
    processes: list[ProcessRecord] | None = None,
    process_cap: int = DEFAULT_PROCESS_CAP,
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

    is_mantigi = "## BAĞLAYICI İŞ KURALLARI (HARFİYEN UY)\n"
    for i, br in enumerate(rules, 1):
        is_mantigi += f"{i}. {br}\n"

    return f"""Sen KVKK (6698) ve GDPR (2016/679) uzmanı bir hukuk asistanısın.
Kullanıcı '{doc_type}' türünde bir doküman istiyor. Aşağıdaki BAĞLAYICI çerçevenin
dışına çıkma; kendi kafandan hukuki prosedür, dayanak, süre veya şablon uydurma.

{is_mantigi}
{surec_metni}
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
