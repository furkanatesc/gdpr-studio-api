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
    """Satırları kategoriye göre grupla; her alanı clean_tokens ile birleştir (boş→boş)."""
    acc: dict[str, dict[str, list[str]]] = {}
    for row in rows:
        cat = _norm(row.get("kategori", ""))
        if not cat:
            continue
        bucket = acc.setdefault(cat, {f: [] for f in CATALOG_FIELDS})
        for f in CATALOG_FIELDS:
            bucket[f].extend(row.get(f, []) or [])
    return {
        cat: {f: clean_tokens(vals) for f, vals in fields.items()}
        for cat, fields in acc.items()
    }


def merge_catalog(base: dict[str, dict], *sources: dict[str, dict]) -> dict[str, dict]:
    """Mevcut katalog + N kaynak → alan-birleşimli katalog. Yeni kategori eklenir; boş→boş.

    base'te olmayan alan anahtarları (ör. 'kaynaklar') korunur.
    """
    cats = set(base) | {c for s in sources for c in s}
    out: dict[str, dict] = {}
    for cat in cats:
        contributors = [d.get(cat, {}) for d in (base, *sources) if cat in d]
        keys = {k for c in contributors for k in c}
        merged: dict[str, list[str]] = {}
        for k in keys:
            vals: list[str] = []
            for c in contributors:
                v = c.get(k, [])
                vals.extend(v if isinstance(v, list) else [v])
            merged[k] = clean_tokens([str(x) for x in vals])
        out[cat] = merged
    return out
