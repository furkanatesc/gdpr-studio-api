import io
import zipfile

from app.inventory_template import STANDARD_HEADERS, build_template_xlsx


def test_template_valid():
    content = build_template_xlsx()
    assert content[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        assert any("sheet" in n for n in z.namelist())
    assert "Veri Konusu Kişi Grubu" in STANDARD_HEADERS and len(STANDARD_HEADERS) == 26
