"""CLI orkestrasyon: envanter xlsx + mevcut json (+ rapor json) → zenginleşmiş katalog.

Çalıştırma:
  python -m scripts.enrich_categories --base data/categories.json \
      --xlsx "<yol>/*.xlsx" --report report.json --out data/categories.json --summary ozet.txt
"""

from __future__ import annotations

import argparse
import json
import unicodedata

from .aggregate import aggregate_rows, merge_catalog
from .xlsx_reader import read_inventory_rows


def _load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return {unicodedata.normalize("NFC", k): v for k, v in raw.items()}


def build_enriched(
    base_json_path: str,
    xlsx_paths: list[str],
    report_json_path: str | None = None,
) -> dict[str, dict]:
    """Tüm kaynakları oku → birleşik katalog döndür (saf; dosya yazmaz)."""
    base = _load_json(base_json_path)
    sources: list[dict[str, dict]] = []
    rows: list[dict] = []
    for p in xlsx_paths:
        rows.extend(read_inventory_rows(p))
    if rows:
        sources.append(aggregate_rows(rows))
    if report_json_path:
        sources.append(_load_json(report_json_path))
    return merge_catalog(base, *sources)


def _summary(catalog: dict[str, dict]) -> str:
    lines = [f"{len(catalog)} kategori"]
    for cat in sorted(catalog):
        data = catalog[cat]
        vt = len(data.get("veri_turu", []))
        sak = len(data.get("saklama_sureleri", []))
        idari = len(data.get("idari_tedbirler", []))
        teknik = len(data.get("teknik_tedbirler", []))
        lines.append(f"  {cat}: veri_turu={vt} saklama={sak} idari={idari} teknik={teknik}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Grounding kataloğunu envanter/rapor ile zenginleştir.")
    ap.add_argument("--base", required=True, help="mevcut categories.json")
    ap.add_argument("--xlsx", nargs="*", default=[], help="envanter .xlsx yolları")
    ap.add_argument("--report", default=None, help="deep-research JSON (opsiyonel)")
    ap.add_argument("--out", required=True, help="çıktı categories.json")
    ap.add_argument("--summary", default=None, help="insan-okur özet dosyası (opsiyonel)")
    args = ap.parse_args()
    catalog = build_enriched(args.base, args.xlsx, args.report)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=1, sort_keys=True)
    summary = _summary(catalog)
    if args.summary:
        with open(args.summary, "w", encoding="utf-8") as f:
            f.write(summary)
    print(summary)


if __name__ == "__main__":
    main()
