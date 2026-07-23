"""Belge puanlama — saf/deterministik (DB'siz).

Puan A (zorunlu unsur tamlıği): aydinlatma bolumlerinin m.10 alanlarinin placeholder'siz
dolu olma orani. Boilerplate ile dolan alan (ör. standart aktarim) bolum verisinde bos
sayilir -> muvekkile ozgu doluluk sinyalini verir.
"""

from __future__ import annotations

from legal_core.aggregate_sections import Section


def completeness_score(sections: list[Section]) -> float | None:
    if not sections:
        return None
    filled = 0
    for s in sections:
        filled += bool(s.kategoriler or s.veri_turleri)
        filled += bool(s.amaclar)
        filled += bool(s.hukuki_sebepler)
        filled += bool(s.saklama_sureleri)
        filled += bool(s.aktarim)
        filled += bool(s.toplama)
    total = 6 * len(sections)
    return filled / total
