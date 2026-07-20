"""Combobox seçenekleri — kanonik kategori adları + amaçlar (categories.json)."""

from __future__ import annotations

import json
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "data" / "categories.json"


def grounding_options() -> dict:
    raw = json.loads(_PATH.read_text(encoding="utf-8"))
    kategoriler = sorted(raw.keys())
    amaclar = sorted({a for v in raw.values() for a in v.get("amaclar", [])})
    return {"kategoriler": kategoriler, "amaclar": amaclar}
