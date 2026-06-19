"""Prompt kurulumu — envanter + iş kuralları + kullanıcı girdisini birleştirir.

worker.py'nin prompt mantığı buraya saf olarak taşındı. DISCLAIMER emoji'sizdir
(web kopyasıyla tutarlı). build_prompt yalnızca string üretir; model çağrısı yapmaz.
"""

from __future__ import annotations

import json

from .models import InventoryRecord

# Her çıktının en altına eklenen zorunlu uyarı (hooks.json playbook'u ile uyumlu).
DISCLAIMER = (
    "Bu çıktı avukat incelemesine tabi hukuki taslaktır. Hukuki tavsiye niteliği "
    "taşımaz. Her karar ve resmi belge, konuya hâkim bir hukukçu tarafından "
    "incelenmeli ve onaylanmalıdır."
)

# Disclaimer'ın yeniden eklenip eklenmeyeceğini saptamak için sabit anahtar ifade.
DISCLAIMER_MARKER = "avukat incelemesine tabi"


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


def build_prompt(
    doc_type: str,
    user_input: dict,
    inventory: list[InventoryRecord],
    rules: list[str],
) -> str:
    """Tam üretim prompt'unu kurar (model-agnostik)."""
    kurallar_metni = "## KVKK ENVANTERİ — BAĞLAYICI KAYITLAR\n" + format_inventory(inventory)

    is_mantigi = "## BAĞLAYICI İŞ KURALLARI (HARFİYEN UY)\n"
    for i, br in enumerate(rules, 1):
        is_mantigi += f"{i}. {br}\n"

    return f"""Sen KVKK (6698) ve GDPR (2016/679) uzmanı bir hukuk asistanısın.
Kullanıcı '{doc_type}' türünde bir doküman istiyor. Aşağıdaki BAĞLAYICI çerçevenin
dışına çıkma; kendi kafandan hukuki prosedür, dayanak, süre veya şablon uydurma.

{is_mantigi}

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
