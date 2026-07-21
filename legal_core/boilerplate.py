"""Aydınlatma metni boilerplate yükleyici.

data/aydinlatma_boilerplate.json içeriği avukat onayına tabi taslak metindir
(avukata_oneri onay akışına bağlanacaktır). Bu modül yalnızca 5 içerik anahtarını
okuyup NFC normalize ederek döndürür; JSON'daki `_note` gibi meta anahtarlar
filtrelenir.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path

_PATH = Path(__file__).resolve().parent.parent / "data" / "aydinlatma_boilerplate.json"
_KEYS = ("tanimlar", "kaynaklar", "ortak_hukumler", "haklar_m11", "basvuru_usulu")


def load_boilerplate() -> dict[str, str]:
    raw = json.loads(_PATH.read_text(encoding="utf-8"))

    missing = [k for k in _KEYS if k not in raw]
    if missing:
        raise KeyError(f"aydinlatma_boilerplate.json eksik anahtar(lar): {missing}")

    result = {}
    for key in _KEYS:
        value = unicodedata.normalize("NFC", str(raw[key]))
        if not value.strip():
            raise ValueError(f"aydinlatma_boilerplate.json boş içerik: {key!r}")
        result[key] = value
    return result
