"""Uretilen Aydinlatma Metni (Markdown) icin minimal .docx donusturucu."""

import io

from docx import Document


def render_docx(markdown_text: str, title: str) -> bytes:
    """markdown_text'i basit bir Word belgesine cevirir, bayt olarak dondurur."""
    doc = Document()
    doc.add_heading(title, level=0)

    for line in markdown_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### "):
            doc.add_heading(stripped[4:], level=3)
        elif stripped.startswith("## "):
            doc.add_heading(stripped[3:], level=2)
        elif stripped.startswith("# "):
            doc.add_heading(stripped[2:], level=1)
        elif stripped.startswith("- ") or stripped.startswith("* "):
            doc.add_paragraph(stripped[2:], style="List Bullet")
        else:
            doc.add_paragraph(stripped)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
