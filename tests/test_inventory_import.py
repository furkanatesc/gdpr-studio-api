import io
import zipfile

import pytest

from app.inventory_import import InventoryImportError, parse_inventory_xlsx


def _xlsx(header, rows):
    strings = []
    def sid(v):
        if v not in strings:
            strings.append(v)
        return strings.index(v)
    cells = []
    for ri, row in enumerate([header] + rows, 1):
        cs = "".join(f'<c r="{chr(65+ci)}{ri}" t="s"><v>{sid(v)}</v></c>' for ci, v in enumerate(row))
        cells.append(f'<row r="{ri}">{cs}</row>')
    ss = "".join(f"<si><t>{s}</t></si>" for s in strings)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/sharedStrings.xml", f'<sst xmlns="x">{ss}</sst>')
        z.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="x"><sheetData>{"".join(cells)}</sheetData></worksheet>')
    return buf.getvalue()


def test_parse_groups_rows():
    content = _xlsx(
        ["Departman", "İş Süreci", "Alt Süreç", "Veri Konusu Kişi Grubu", "Kişisel Veri Kategorisi"],
        [["İK", "İşe Giriş", "Kimlik", "Çalışan", "Kimlik"], ["İK", "İşe Giriş", "Kimlik", "Çalışan", "İletişim"]],
    )
    procs = parse_inventory_xlsx(content, sector="otel")
    assert len(procs) == 1 and procs[0]["kisi_grubu"] == "Çalışan"
    assert procs[0]["data"]["kategoriler"] == ["Kimlik", "İletişim"]


def test_parse_rejects_non_xlsx():
    with pytest.raises(InventoryImportError):
        parse_inventory_xlsx(b"not a zip", sector="otel")
