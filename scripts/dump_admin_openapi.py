"""Dump admin-api OpenAPI to a file for admin-web type generation.
Run with the pinned .venv: backend/.venv/Scripts/python.exe scripts/dump_admin_openapi.py
"""
import json
import sys
from pathlib import Path

from admin_api.main import app

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../admin-web/openapi.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(app.openapi(), indent=2), encoding="utf-8")
print(f"wrote {out}")
