"""Anket sihirbazı soru şeması — departman/bölüm/soru + Listeler vocab (anket_sorular.json)."""

from __future__ import annotations

import json
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "data" / "anket_sorular.json"


def load_survey_schema() -> dict:
    if not _PATH.exists():
        raise FileNotFoundError(f"Anket soru şeması bulunamadı: {_PATH}")
    return json.loads(_PATH.read_text(encoding="utf-8"))
