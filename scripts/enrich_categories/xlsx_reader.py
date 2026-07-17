"""xlsx okuma — stdlib zipfile+XML (yeni bağımlılık yok). Saf parser + ince sarmalayıcı."""

from __future__ import annotations

import re
import zipfile
from html import unescape

from .mapping import row_to_record


def parse_shared_strings(xml: str) -> list[str]:
    out: list[str] = []
    for si in re.findall(r"<si>(.*?)</si>", xml, re.S):
        texts = re.findall(r"<t[^>]*>(.*?)</t>", si, re.S)
        out.append(unescape("".join(texts)))
    return out


def _col_index(ref: str) -> int:
    letters = re.match(r"[A-Z]+", ref)
    if not letters:
        return 0
    idx = 0
    for ch in letters.group(0):
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def parse_worksheet(xml: str, shared: list[str]) -> list[list[str]]:
    """Satırların hücre-değeri listesi (sütun sırası korunur, boş hücreler '' ile dolar)."""
    rows: list[list[str]] = []
    for r in re.findall(r"<row[^>]*>(.*?)</row>", xml, re.S):
        cells: dict[int, str] = {}
        for c in re.findall(r"<c\b[^>]*>.*?</c>|<c\b[^>]*/>", r, re.S):
            ref_m = re.search(r'r="([A-Z]+\d+)"', c)
            col = _col_index(ref_m.group(1)) if ref_m else len(cells)
            t_m = re.search(r't="([^"]+)"', c)
            typ = t_m.group(1) if t_m else "n"
            if typ == "inlineStr":
                txts = re.findall(r"<t[^>]*>(.*?)</t>", c, re.S)
                cells[col] = unescape("".join(txts))
                continue
            v_m = re.search(r"<v>(.*?)</v>", c, re.S)
            val = unescape(v_m.group(1)) if v_m else ""
            if typ == "s":
                try:
                    val = shared[int(val)]
                except (ValueError, IndexError):
                    pass
            cells[col] = val
        width = (max(cells) + 1) if cells else 0
        rows.append([cells.get(i, "") for i in range(width)])
    return rows


def read_inventory_rows(path: str) -> list[dict]:
    """xlsx'in tüm sayfalarını oku; ilk dolu satırı başlık kabul et; kayıtlara çevir."""
    records: list[dict] = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared = (
            parse_shared_strings(z.read("xl/sharedStrings.xml").decode("utf-8", "ignore"))
            if "xl/sharedStrings.xml" in names
            else []
        )
        sheets = sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        for name in sheets:
            rows = parse_worksheet(z.read(name).decode("utf-8", "ignore"), shared)
            header = next((r for r in rows if any(c.strip() for c in r)), None)
            if header is None:
                continue
            start = rows.index(header) + 1
            for row in rows[start:]:
                rec = row_to_record(header, row)
                if rec is not None:
                    records.append(rec)
    return records
