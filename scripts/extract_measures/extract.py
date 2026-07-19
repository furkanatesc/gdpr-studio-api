"""Envanter sayfalarından güvenlik tedbirlerini global düz liste olarak çıkarır.

KVKK dokümanlarında teknik/idari tedbirler org-geneli standart bir listedir
(kategoriye bağlı değil). Kaynak: başlığı 'tedbir' içeren sütunların hücreleri
(sayfa-3'ün 'Tedbirler' düz listesi + varsa sayfa-1'in idari/teknik sütunları).
"""

from __future__ import annotations

import re
import unicodedata
import zipfile

from scripts.enrich_categories.aggregate import clean_tokens
from scripts.enrich_categories.xlsx_reader import parse_shared_strings, parse_worksheet

# Baştaki sıra numarası öneki: "1.", "2-", "12)" — tedbir metninin parçası değil.
# NOT: "3. şahıs..." gibi sıra-sıfatı önekini de kırpardı → gerçek metin kaybı riski. Mevcut
# 41 tedbirde böyle bir değer yok (denetlendi); yeni kaynak eklenirse çıktı insan denetlenmeli.
_PREFIX = re.compile(r"^\s*\d+\s*[.\-)]\s*")
# Başlığın kendisi hücreye düşerse ele (veri değil).
_HEADER_JUNK = {"tedbirler", "idari guvenlik tedbiri", "teknik guvenlik tedbiri", "tedbir"}
# İnsan denetiminde (plan Step 6) tespit edilen tedbir-olmayan değerler (açık, gözden geçirilmiş):
# "Diğer" = checklist catch-all ("41.Diğer"); "Web Sunucu" = E-Ticaret İdari Tedbir sütununda
# 33× tekrarlanan yanlış değer (veri-kalitesi hatası) — hiçbiri güvenlik tedbiri değil.
_MEASURE_JUNK = {"diğer", "web sunucu"}
# Tedbir hücrelerinde satır sonu/noktalı virgül gerçek öğe ayracıdır; VİRGÜL değildir —
# kaynakta bir hücre = bir tam tedbir cümlesi, virgül cümle-içi noktalamadır
# (ör. "Erişim, bilgi güvenliği, kullanım, saklama ve imha konularında...").
# scripts.enrich_categories.mapping.split_cell virgülü de ayraç sayar (kategorili çok-değerli
# sütunlar için doğrudur) — burada kullanılırsa tek bir tedbir cümlesi anlamsız parçalara
# bölünür (uydurma/veri bozma riski). Bu yüzden mapping.split_cell BİLEREK reuse EDİLMEDİ;
# yerine sadece \n/; ayıran yerel bir bölme kullanılır.
_ITEM_SPLIT = re.compile(r"[\n;]")


def _split_measure_cell(value: str) -> list[str]:
    """Tedbir hücresini yalnız satır sonu/noktalı virgülle böler (virgülle BÖLMEZ)."""
    if not value:
        return []
    return [p.strip() for p in _ITEM_SPLIT.split(value) if p.strip()]


def _hnorm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s).strip().lower())


def strip_measure_prefix(s: str) -> str:
    return _PREFIX.sub("", s).strip()


def read_measures(path: str) -> list[str]:
    """xlsx'in tüm sayfalarında başlığı 'tedbir' içeren sütunların boş-olmayan hücreleri."""
    out: list[str] = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared = (
            parse_shared_strings(z.read("xl/sharedStrings.xml").decode("utf-8", "ignore"))
            if "xl/sharedStrings.xml" in names else []
        )
        sheets = sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        for name in sheets:
            rows = parse_worksheet(z.read(name).decode("utf-8", "ignore"), shared)
            header = next((r for r in rows if any(c.strip() for c in r)), None)
            if header is None:
                continue
            cols = [i for i, h in enumerate(header) if "tedbir" in _hnorm(h)]
            if not cols:
                continue
            for row in rows[rows.index(header) + 1:]:
                for ci in cols:
                    if ci >= len(row):
                        continue
                    for piece in _split_measure_cell(row[ci]):
                        val = strip_measure_prefix(piece)
                        nv = _hnorm(val)
                        if val and nv not in _HEADER_JUNK and nv not in _MEASURE_JUNK:
                            out.append(val)
    return out


def build_measures(paths: list[str]) -> list[str]:
    """6 dosyadan union + NFC/case dedupe (ilk yazım korunur)."""
    all_vals: list[str] = []
    for p in paths:
        all_vals.extend(read_measures(p))
    return clean_tokens(all_vals)
