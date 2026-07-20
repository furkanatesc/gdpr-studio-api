"""Yüklenen KVKK envanteri (xlsx) → süreç kayıtları. Parse mantığı extract_processes ile aynı."""

from __future__ import annotations

import io
import re
import zipfile

from scripts.enrich_categories.xlsx_reader import parse_shared_strings, parse_worksheet
from scripts.extract_processes.aggregate import aggregate_processes
from scripts.extract_processes.mapping import row_to_process


class InventoryImportError(Exception):
    pass


def parse_inventory_xlsx(content: bytes, sector: str) -> list[dict]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as e:
        raise InventoryImportError("Geçerli bir .xlsx dosyası değil.") from e
    with zf as z:
        names = z.namelist()
        shared = (
            parse_shared_strings(z.read("xl/sharedStrings.xml").decode("utf-8", "ignore"))
            if "xl/sharedStrings.xml" in names else []
        )
        sheets = sorted(n for n in names if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        if not sheets:
            raise InventoryImportError("Sayfa bulunamadı.")
        rows = parse_worksheet(z.read(sheets[0]).decode("utf-8", "ignore"), shared)
    header = next((r for r in rows if any(c.strip() for c in r)), None)
    if header is None:
        raise InventoryImportError("Başlık satırı bulunamadı.")
    records = [rec for row in rows[rows.index(header) + 1:] if (rec := row_to_process(header, row)) is not None]
    if not records:
        raise InventoryImportError("Envanterde geçerli satır (kişi grubu dolu) bulunamadı.")
    return aggregate_processes(records, sector)
