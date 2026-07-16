"""Saf toplama/temizleme yardımcıları — grounding katalog zenginleştirme.

Uydurma yasak: yalnız kaynak değerler alınır, boş→boş kalır. Muhafazakâr temizlik
(çöp at + case-insensitive dedupe); yazım düzeltme/terim birleştirme YOK.
"""

from __future__ import annotations

import unicodedata

_JUNK = {"", "???", "??", "-", "--", "n/a", "na", "bilinmiyor", "belirsiz", "yok"}

CATALOG_FIELDS = (
    "veri_turu",
    "kisi_grubu",
    "departmanlar",
    "amaclar",
    "hukuki_sebepler",
    "saklama_sureleri",
    "idari_tedbirler",
    "teknik_tedbirler",
)


def _norm(s: str) -> str:
    return unicodedata.normalize("NFC", s.strip())


def clean_tokens(values: list[str]) -> list[str]:
    """Strip+NFC, çöp at, case-insensitive dedupe (ilk yazım korunur), sıra-kararlı."""
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        n = _norm(v)
        key = n.lower()
        if key in _JUNK or key in seen:
            continue
        seen.add(key)
        out.append(n)
    return out


def aggregate_rows(rows: list[dict]) -> dict[str, dict]:
    """Satırları kategoriye göre grupla; her alanı clean_tokens ile birleştir (boş→boş).

    Kategori anahtarları büyük/küçük-harf DUYARSIZ gruplanır ("Ve"/"ve", "hukuki"/"Hukuki"
    aynı kategoridir); görüntü adı ilk görülen yazımdır.
    """
    acc: dict[str, dict[str, list[str]]] = {}
    display: dict[str, str] = {}
    for row in rows:
        cat = _norm(row.get("kategori", ""))
        if not cat:
            continue
        key = cat.casefold()
        display.setdefault(key, cat)
        bucket = acc.setdefault(key, {f: [] for f in CATALOG_FIELDS})
        for f in CATALOG_FIELDS:
            bucket[f].extend(row.get(f, []) or [])
    return {
        display[key]: {f: clean_tokens(vals) for f, vals in fields.items()}
        for key, fields in acc.items()
    }


def merge_catalog(base: dict[str, dict], *sources: dict[str, dict]) -> dict[str, dict]:
    """Mevcut katalog + N kaynak → alan-birleşimli katalog. Yeni kategori eklenir; boş→boş.

    Kategoriler büyük/küçük-harf duyarsız birleşir (görüntü adı ilk görülen, base öncelikli).
    base'te olmayan alan anahtarları (ör. 'kaynaklar') korunur. Tümü-boş kategori düşülür.
    """
    display: dict[str, str] = {}
    order: list[str] = []
    for d in (base, *sources):
        for cat in d:
            key = _norm(cat).casefold()
            if key not in display:
                display[key] = _norm(cat)
                order.append(key)

    out: dict[str, dict] = {}
    for key in order:
        contributors = [
            fields for d in (base, *sources) for cat, fields in d.items()
            if _norm(cat).casefold() == key
        ]
        field_keys = {k for c in contributors for k in c}
        merged: dict[str, list[str]] = {}
        for fk in field_keys:
            vals: list[str] = []
            for c in contributors:
                v = c.get(fk, [])
                vals.extend(v if isinstance(v, list) else [v])
            merged[fk] = clean_tokens([str(x) for x in vals])
        if any(merged.get(f) for f in merged):  # tümü-boş kabuk kategoriyi ekleme
            out[display[key]] = merged
    return out
