"""Türkçe-duyarlı metin normalizasyonu (grounding eşleştirmesi için).

db_retriever._norm'dan birebir taşındı. Kritik: kategori anahtarları kaynakta
bazen NFD (decomposed) tutulduğundan NFC zorunludur; ayrıca Türkçe I/ı
belirsizliği için son adımda dotless 'ı' noktalı 'i'ye katlanır (yalnızca
eşleştirme amaçlı — gösterimde kullanılmaz).
"""

import unicodedata


def norm(s: object) -> str:
    """Eşleştirme için sağlam normalize: NFC + küçült + kırp + ı/i katlaması."""
    if not s:
        return ""
    text = unicodedata.normalize("NFC", str(s))
    text = (
        text.replace("İ", "i")
        .replace("I", "ı")
        .replace("Ğ", "ğ")
        .replace("Ü", "ü")
        .replace("Ş", "ş")
        .replace("Ö", "ö")
        .replace("Ç", "ç")
    )
    text = text.casefold().strip()
    return text.replace("ı", "i")
