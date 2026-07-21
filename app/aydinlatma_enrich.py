"""Bos Section alanlari icin global grounding'den oneri toplar.

Saf, deterministik; oneriler ayri `oneriler` alanindadir, section degerlerine
karismaz (onay T6/T7'de kullanicida). aktarim/toplama icin grounding karsiligi
olmadigindan hicbir zaman onerilmez.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from legal_core.aggregate_sections import Section, _merge_dedup

ENRICHABLE = ["kategoriler", "veri_turleri", "amaclar", "hukuki_sebepler", "saklama_sureleri"]


@dataclass(frozen=True)
class EnrichedSection:
    is_sureci: str
    kisi_gruplari: list[str] = field(default_factory=list)
    kategoriler: list[str] = field(default_factory=list)
    veri_turleri: list[str] = field(default_factory=list)
    amaclar: list[str] = field(default_factory=list)
    hukuki_sebepler: list[str] = field(default_factory=list)
    saklama_sureleri: list[str] = field(default_factory=list)
    aktarim: list[str] = field(default_factory=list)
    toplama: list[str] = field(default_factory=list)
    oneriler: dict[str, list[str]] = field(default_factory=dict)


def enrich_sections(sections: list[Section], sector: str, repo) -> list[EnrichedSection]:
    result: list[EnrichedSection] = []
    for section in sections:
        candidates = []
        for kisi_grubu in section.kisi_gruplari:
            candidates.extend(repo.by_sector_and_group(sector, kisi_grubu))

        if section.kategoriler:
            target_categories = set(section.kategoriler)
            candidates = [
                c for c in candidates if target_categories & set(c.kategoriler)
            ]

        oneriler: dict[str, list[str]] = {}
        for fieldname in ENRICHABLE:
            if getattr(section, fieldname):
                continue
            merged = _merge_dedup(*(getattr(c, fieldname) for c in candidates))
            if merged:
                oneriler[fieldname] = merged

        result.append(
            EnrichedSection(
                is_sureci=section.is_sureci,
                kisi_gruplari=section.kisi_gruplari,
                kategoriler=section.kategoriler,
                veri_turleri=section.veri_turleri,
                amaclar=section.amaclar,
                hukuki_sebepler=section.hukuki_sebepler,
                saklama_sureleri=section.saklama_sureleri,
                aktarim=section.aktarim,
                toplama=section.toplama,
                oneriler=oneriler,
            )
        )
    return result
