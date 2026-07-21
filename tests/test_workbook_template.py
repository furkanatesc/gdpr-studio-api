import io
import zipfile

import openpyxl

from app.workbook_import import parse_workbook_xlsx
from app.workbook_template import build_workbook_template_xlsx


def test_workbook_template_valid_xlsx():
    content = build_workbook_template_xlsx()
    assert isinstance(content, bytes)
    assert content
    assert content[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        assert any("sheet" in n for n in z.namelist())


def test_workbook_template_has_department_sheet():
    content = build_workbook_template_xlsx()
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True)
    assert any(name.startswith("01-Genel") for name in wb.sheetnames)


def test_workbook_template_parses_blank():
    content = build_workbook_template_xlsx()
    result = parse_workbook_xlsx(content, "sirket")
    assert result["processes"] == []
