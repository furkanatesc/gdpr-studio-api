"""Üretilen doküman üzerinde hukuki-doğruluk kontrolleri (objektif, deterministik).

Her kontrol bir CheckResult döndürür. Madde atıfları Türkçe'nin değişken biçimlerine
(m.10 / m. 10 / 10. madde / 10. maddesi / madde 10) toleranslıdır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from legal_core.prompt import DISCLAIMER_MARKER

# Saklama süresi "uydurulmadı" işaretleri: model değeri envanterde yoksa bunlardan
# birini bırakmalı (icat etmek yerine avukata devretmeli).
RETENTION_PLACEHOLDER_MARKERS = [
    "avukat tarafından",
    "veri sorumlusu tarafından",
    "belirlenecek",
    "doldurulacak",
]


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


def cites_article(text: str, n: int) -> bool:
    """Metin, n numaralı maddeye (KVKK/GDPR fark etmeksizin) atıf yapıyor mu?"""
    patterns = [
        rf"m\.?\s*{n}\b",                         # m.10 / m. 10
        rf"\bmadde\s*{n}\b",                      # madde 10
        rf"\b{n}\s*[\.\)]\s*madde",               # 10. madde / 10) madde
        rf"\b{n}\s*(?:inci|ıncı|uncu|üncü|nci)\s*madde",  # 10 uncu madde
    ]
    return any(re.search(p, text, re.IGNORECASE) for p in patterns)


def check_articles(text: str, articles: list[int]) -> CheckResult:
    missing = [a for a in articles if not cites_article(text, a)]
    return CheckResult(
        "madde_atıfları",
        not missing,
        "tümü mevcut" if not missing else f"eksik madde: {missing}",
    )


def check_sections(text: str, keywords: list[str]) -> CheckResult:
    low = text.lower()
    missing = [k for k in keywords if k.lower() not in low]
    return CheckResult(
        "zorunlu_bölümler",
        not missing,
        "tümü mevcut" if not missing else f"eksik: {missing}",
    )


def check_disclaimer(text: str) -> CheckResult:
    ok = DISCLAIMER_MARKER in text
    return CheckResult("disclaimer", ok, "var" if ok else "EKSİK — avukat-onayı uyarısı yok")


def check_special_category(text: str) -> CheckResult:
    """Özel nitelikli veri varsa: m.6 atfı + (açık rıza veya 'özel nitelik') vurgusu."""
    low = text.lower()
    has_m6 = cites_article(text, 6)
    has_context = ("özel nitelik" in low) or ("açık rıza" in low)
    ok = has_m6 and has_context
    return CheckResult(
        "özel_nitelikli_m6",
        ok,
        "m.6 + bağlam var" if ok else f"m.6={has_m6}, bağlam(özel nitelik/açık rıza)={has_context}",
    )


def check_retention_not_fabricated(text: str) -> CheckResult:
    """Envanterde saklama süresi yoktu → model uydurmamalı, placeholder bırakmalı."""
    low = text.lower()
    ok = any(m in low for m in RETENTION_PLACEHOLDER_MARKERS)
    return CheckResult(
        "saklama_uydurma_yasağı",
        ok,
        "placeholder bırakıldı (uydurulmadı)" if ok else "placeholder YOK — süre uydurulmuş olabilir",
    )
