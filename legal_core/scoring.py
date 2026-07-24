"""Belge puanlama — saf/deterministik (DB'siz).

Puan A (zorunlu unsur tamlıği): aydinlatma bolumlerinin m.10 alanlarinin placeholder'siz
dolu olma orani. Boilerplate ile dolan alan (ör. standart aktarim) bolum verisinde bos
sayilir -> muvekkile ozgu doluluk sinyalini verir.
"""

from __future__ import annotations

from legal_core.aggregate_sections import Section
from legal_core.models import ProcessRecord


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


def cerez_completeness_score(has_identity: bool, kategoriler: list[str], tools: str, cmp: str) -> float:
    """Cerez politikasinin 4 zorunlu unsurunun girdi tamligi (avukat_bilgilendirme.md madde 10)."""
    filled = 0
    filled += bool(has_identity)              # veri sorumlusu kimligi (muvekkil)
    filled += bool(kategoriler)               # >=1 cerez kategorisi
    filled += bool(tools.strip())             # 3. taraf araclar/cerezler
    filled += cmp.strip().lower() not in ("", "yok")  # riza mekanizmasi (CMP)
    return filled / 4


def kayit_completeness_score(records: list[ProcessRecord]) -> float | None:
    """Isleme kaydi zorunlu VERBIS alanlarinin envanter satirlarindaki doluluk orani
    (isleme_envanteri zorunlu unsurlari; avukat_bilgilendirme.md'de belgelenir)."""
    if not records:
        return None
    filled = 0
    for r in records:
        filled += bool(r.kisi_grubu)
        filled += bool(r.kategoriler or r.veri_turleri)
        filled += bool(r.amaclar)
        filled += bool(r.hukuki_sebepler)
        filled += bool(r.saklama_sureleri)
        filled += bool(r.aktarim)
    return filled / (6 * len(records))
