"""OpenAPI şemasını `openapi.json`'a yazar — web `api-types` üretiminin tek kaynağı.

Kontrat (GenerateRequest/Response, GroundingRecord, DocType) FastAPI'den deterministik
üretilir; web tarafı bu dosyadan TS tipleri türetir. Böylece sözleşme tek yerde yaşar.

Çalıştırma:  python -m app.export_openapi
CI bunu yeniden üretip commit'li dosyayla karşılaştırır (drift guard — bkz. test_openapi_export).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app

OUTPUT = Path(__file__).resolve().parent.parent / "openapi.json"


def export() -> str:
    """OpenAPI şemasını kararlı (sıralı, girintili) JSON metni olarak döndürür."""
    schema = app.openapi()
    return json.dumps(schema, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> None:
    OUTPUT.write_text(export(), encoding="utf-8")
    print(f"OpenAPI yazıldı: {OUTPUT}")


if __name__ == "__main__":
    main()
