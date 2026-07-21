"""Anket kitabı şablonu indirme (kitap değiştirilmeden)."""

from __future__ import annotations

from pathlib import Path

_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "data" / "anket_kitabi_sablon.xlsx"


def build_workbook_template_xlsx() -> bytes:
    if not _TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Anket kitabı şablonu bulunamadı: {_TEMPLATE_PATH}")
    return _TEMPLATE_PATH.read_bytes()
