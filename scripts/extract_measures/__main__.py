"""CLI: envanterlerden global tedbir listesi üretir.

Çalıştırma:
  python -m scripts.extract_measures --xlsx <yol1> <yol2> --out data/measures.json
"""

from __future__ import annotations

import argparse
import json

from .extract import build_measures


def main() -> None:
    ap = argparse.ArgumentParser(description="Envanterlerden global tedbir listesi üret.")
    ap.add_argument("--xlsx", nargs="+", required=True, help="envanter .xlsx yolları")
    ap.add_argument("--out", required=True, help="çıktı measures.json")
    args = ap.parse_args()
    measures = build_measures(args.xlsx)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"tedbirler": measures}, f, ensure_ascii=False, indent=1)
    print(f"{len(measures)} tedbir yazıldı: {args.out}")


if __name__ == "__main__":
    main()
