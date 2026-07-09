"""Uyum skoru + otomatik sinyal değerlendirmesi — saf mantık (DB'siz, test edilebilir)."""
from __future__ import annotations


def compute_score(yapildi: int, total: int, uygulanmaz: int) -> float | None:
    payda = total - uygulanmaz
    if payda <= 0:
        return None
    return yapildi / payda


def evaluate_auto_signal(auto_signal: str, generated_doc_types: set[str]) -> str | None:
    prefix = "doc_generated:"
    if auto_signal.startswith(prefix):
        return "yapildi" if auto_signal[len(prefix):] in generated_doc_types else "eksik"
    return None  # kaynağı olmayan/bilinmeyen sinyal
