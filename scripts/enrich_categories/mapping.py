"""Envanter sütun başlığı → katalog alanı eşlemesi + çok-değerli hücre bölme."""

from __future__ import annotations

import re
import unicodedata

# Envanter (VERBİS/RoPA) başlığı → katalog alanı. 'kategori' anahtar sütunudur.
_RAW_MAP = {
    "Kişisel Veri Kategorisi": "kategori",
    "Veri Türü": "veri_turu",
    "Veri Konusu Kişi Grubu": "kisi_grubu",
    "Departman": "departmanlar",
    "Veri Kullanım Amacı": "amaclar",
    "Hukuki Sebep": "hukuki_sebepler",
    "Azami Süre (Saklama)": "saklama_sureleri",
    "İdari Güvenlik Tedbiri": "idari_tedbirler",
    "Teknik Güvenlik Tedbiri": "teknik_tedbirler",
}


def _hnorm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).strip().lower()
    return re.sub(r"\s+", " ", s)


HEADER_TO_FIELD = {_hnorm(k): v for k, v in _RAW_MAP.items()}

# Envanterlerde kategori hücreleri numaralı önek taşıyabilir ("1- Kimlik", "12- Pazarlama").
# Bu bir sıra numarası; kategori adı değil → temizlenir ki "Kimlik" ile birleşsin.
_NUM_PREFIX = re.compile(r"^\s*\d+\s*[-–—.)]\s*")


def canonical_category(name: str) -> str:
    """Kategori adını kanonikleştir: NFC + numaralı önek at + iç boşluğu tekle."""
    n = unicodedata.normalize("NFC", name).strip()
    n = _NUM_PREFIX.sub("", n)
    return re.sub(r"\s+", " ", n).strip()


def split_cell(value: str) -> list[str]:
    """Hücreyi \\n / ; / , ile böler; parçaları trimler, boşları atar."""
    if not value:
        return []
    parts = re.split(r"[\n;,]", value)
    return [p.strip() for p in parts if p.strip()]


def row_to_record(header_row: list[str], cells: list[str]) -> dict | None:
    """Başlık eşlemesiyle satırı {'kategori':..., <alan>: [..]}'e çevirir; kategori boşsa None."""
    rec: dict[str, object] = {"kategori": ""}
    for i, head in enumerate(header_row):
        field = HEADER_TO_FIELD.get(_hnorm(head))
        if field is None or i >= len(cells):
            continue
        val = cells[i]
        if field == "kategori":
            rec["kategori"] = canonical_category(val)
        else:
            rec[field] = split_cell(val)
    return rec if rec["kategori"] else None
