"""Uyum skoru + otomatik sinyal değerlendirmesi — saf mantık (DB'siz, test edilebilir)."""
from __future__ import annotations


def compute_score(yapildi: int, total: int, uygulanmaz: int) -> float | None:
    payda = total - uygulanmaz
    if payda <= 0:
        return None
    return yapildi / payda


def evaluate_auto_signal(auto_signal: str, generated_doc_types: set[str]) -> str | None:
    prefix = "doc_generated:"
    if auto_signal.startswith(prefix):
        return "yapildi" if auto_signal[len(prefix):] in generated_doc_types else "eksik"
    return None  # kaynağı olmayan/bilinmeyen sinyal


DOC_TYPE_COMPLIANCE_KEYS: dict[str, list[str]] = {
    "aydinlatma": [
        "aydinlatma_metni", "aydinlatma_kanallari", "hukuki_sebep_eslemesi",
        "basvuru_sureci", "haklar_karsilanmasi", "isleme_envanteri",
    ],
    "cerez": ["cerez_politikasi", "aydinlatma_kanallari", "acik_riza_yonetimi"],
    "kayit": ["isleme_envanteri", "verbis_kaydi", "hukuki_sebep_eslemesi", "saklama_imha_politikasi"],
    "dpa": ["veri_isleyen_sozlesmeleri", "yurtdisi_aktarim"],
    "dpia": ["dpia", "ozel_nitelikli_veri"],
    "ihlal": ["ihlal_mudahale_plani", "ihlal_bildirim_72saat"],
}


def compliance_snapshot_score(statuses: dict[str, str], doc_type: str) -> float | None:
    """Belge turunun ilgili uyum maddelerinin org checklist durumundan karsilanma orani."""
    keys = DOC_TYPE_COMPLIANCE_KEYS.get(doc_type)
    if not keys:
        return None
    total = len(keys)
    uygulanmaz = sum(1 for k in keys if statuses.get(k) == "uygulanmaz")
    yapildi = sum(1 for k in keys if statuses.get(k) == "yapildi")
    return compute_score(yapildi, total, uygulanmaz)
