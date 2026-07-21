import io
import zipfile

import docx

from app.docx_export import render_docx

MARKDOWN = (
    "## Baslik\n\nBir paragraf.\n\n- madde bir\n- madde iki\n\n"
    "Bu cikti avukat incelemesine tabidir, hukuki tavsiye yerine gecmez."
)
TITLE = "Aydinlatma Metni"


def test_render_docx_returns_nonempty_bytes():
    result = render_docx(MARKDOWN, TITLE)
    assert isinstance(result, bytes)
    assert len(result) > 0


def test_render_docx_is_valid_zip_with_document_xml():
    result = render_docx(MARKDOWN, TITLE)
    with zipfile.ZipFile(io.BytesIO(result)) as zf:
        assert "word/document.xml" in zf.namelist()


def test_render_docx_contains_title_content_and_disclaimer():
    result = render_docx(MARKDOWN, TITLE)
    doc = docx.Document(io.BytesIO(result))
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert TITLE in full_text
    assert "madde bir" in full_text
    assert "avukat incelemesine tabidir" in full_text
