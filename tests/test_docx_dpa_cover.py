from __future__ import annotations

import io

import docx

from app.docx_export import render_styled_docx


def test_dpa_cover_has_isleyen():
    data = render_styled_docx("## Madde 1\nMetin", "dpa", {
        "veri_sorumlusu": "Acme A.Ş.", "veri_isleyen": "Bulut A.Ş.",
        "tarih": "03.08.2026", "versiyon": "Taslak"})
    assert data[:2] == b"PK"

    doc = docx.Document(io.BytesIO(data))
    t = "\n".join(p.text for p in doc.paragraphs)
    assert "Veri İşleyen" in t
    assert "Bulut A.Ş." in t
    assert "Acme A.Ş." in t
