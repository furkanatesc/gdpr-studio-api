"""CLI: envanter xlsx'lerinden global süreç şablon kütüphanesi üretir.

Çalıştırma:
  python -m scripts.extract_processes --xlsx <yol1> <yol2> --out data/processes.json --summary ozet.txt
"""

from __future__ import annotations

import argparse
import json
import os
import re
import zipfile

from scripts.enrich_categories.xlsx_reader import parse_shared_strings, parse_worksheet

from .aggregate import aggregate_processes
from .mapping import row_to_process, sector_for_filename


def read_process_rows(path: str) -> list[dict]:
    """xlsx'in ilk sayfasını oku → süreç satır kayıtları (kişi grubu olmayan satır düşer)."""
    records: list[dict] = []
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        shared = (
            parse_shared_strings(z.read("xl/sharedStrings.xml").decode("utf-8", "ignore"))
            if "xl/sharedStrings.xml" in names else []
        )
        sheets = sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        if not sheets:
            return records
        rows = parse_worksheet(z.read(sheets[0]).decode("utf-8", "ignore"), shared)
        header = next((r for r in rows if any(c.strip() for c in r)), None)
        if header is None:
            return records
        for row in rows[rows.index(header) + 1:]:
            rec = row_to_process(header, row)
            if rec is not None:
                records.append(rec)
    return records


def build_processes(xlsx_paths: list[str]) -> list[dict]:
    out: list[dict] = []
    for path in xlsx_paths:
        sector = sector_for_filename(os.path.basename(path))
        if sector is None:
            print(f"UYARI: sektör çözülemedi, atlanıyor: {os.path.basename(path)}")
            continue
        rows = read_process_rows(path)
        out.extend(aggregate_processes(rows, sector))
    return out


def _summary(procs: list[dict]) -> str:
    by_sector: dict[str, list[dict]] = {}
    for p in procs:
        by_sector.setdefault(p["sector"], []).append(p)
    lines = [f"{len(procs)} süreç / {len(by_sector)} sektör"]
    for sector in sorted(by_sector):
        items = by_sector[sector]
        groups: dict[str, int] = {}
        for p in items:
            groups[p["kisi_grubu"]] = groups.get(p["kisi_grubu"], 0) + 1
        sak = sum(1 for p in items if p["data"]["saklama_sureleri"])
        lines.append(f"\n  {sector}: {len(items)} süreç, saklama dolu={sak}")
        for g, n in sorted(groups.items(), key=lambda x: -x[1]):
            lines.append(f"      {n:4d}x {g}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Envanterlerden global süreç şablonu üret.")
    ap.add_argument("--xlsx", nargs="+", required=True, help="envanter .xlsx yolları")
    ap.add_argument("--out", required=True, help="çıktı processes.json")
    ap.add_argument("--summary", default=None, help="insan-okur özet dosyası")
    args = ap.parse_args()
    procs = build_processes(args.xlsx)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(procs, f, ensure_ascii=False, indent=1, sort_keys=True)
    summary = _summary(procs)
    if args.summary:
        with open(args.summary, "w", encoding="utf-8") as f:
            f.write(summary)
    print(summary)


if __name__ == "__main__":
    main()
