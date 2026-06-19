"""Drift guard: commit'li openapi.json, FastAPI'nin ürettiği şemayla güncel mi?

Web `api-types` bu dosyadan üretildiği için, kontrat değişip dosya güncellenmezse
web tipleri eskir. Bu test CI'da yakalar.
"""

from __future__ import annotations

from app.export_openapi import OUTPUT, export


def test_openapi_json_guncel():
    committed = OUTPUT.read_text(encoding="utf-8")
    assert committed == export(), (
        "openapi.json güncel değil — `python -m app.export_openapi` çalıştırıp commit'leyin."
    )
