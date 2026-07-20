"""Combobox seçenekleri — kanonik kategori adları + amaçlar (categories.json)."""

from __future__ import annotations

import json
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "data" / "categories.json"

# KVKK m.6/1'in saydığı özel nitelikli veri türlerinin kanonik kategori karşılıkları.
# Kanun metninden türetilmiştir (uydurma yok). Kategori adı değişirse test kırılır —
# aksi halde m.6 uyarısı sessizce kaybolur.
OZEL_NITELIKLI = frozenset({
    "Irk ve Etnik Köken",
    "Siyasi Düşünce Bilgileri",
    "Felsefi İnanç, Din, Mezhep ve Diğer İnançlar",
    "Kılık ve Kıyafet",
    "Dernek Üyeliği",
    "Vakıf Üyeliği",
    "Sendika Üyeliği",
    "Sağlık Bilgileri",
    "Cinsel Hayat",
    "Ceza Mahkûmiyeti Ve Güvenlik Tedbirleri",
    "Biyometrik Veri",
    "Genetik Veri",
})


def grounding_options() -> dict:
    raw = json.loads(_PATH.read_text(encoding="utf-8"))
    kategoriler = sorted(raw.keys())
    amaclar = sorted({a for v in raw.values() for a in v.get("amaclar", [])})
    return {
        "kategoriler": kategoriler,
        "amaclar": amaclar,
        "ozelNitelikli": sorted(OZEL_NITELIKLI),
    }
