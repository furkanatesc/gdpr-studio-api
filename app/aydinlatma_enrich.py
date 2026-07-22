"""Bos Section alanlari icin global grounding'den oneri toplar.

Saf, deterministik; oneriler ayri `oneriler` alanindadir, section degerlerine
karismaz (onay T6/T7'de kullanicida). aktarim/toplama icin grounding karsiligi
olmadigindan hicbir zaman onerilmez.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from legal_core.aggregate_sections import Section, _merge_dedup
from legal_core.canonical import Canonicalizer

ENRICHABLE = ["kategoriler", "veri_turleri", "amaclar", "hukuki_sebepler", "saklama_sureleri"]
# Dolu olsa da EK standart oneri sunulan alanlar (avukat S2: birden fazla amac onerisi,
# ekle/cikar). Digerleri yalniz BOS alanda onerilir.
ADDITIVE = {"amaclar"}


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


def enrich_sections(
    sections: list[Section],
    sector: str,
    repo,
    canonicalizer: Canonicalizer | None = None,
) -> list[EnrichedSection]:
    result: list[EnrichedSection] = []
    for section in sections:
        if canonicalizer is None:
            candidates = []
            for kisi_grubu in section.kisi_gruplari:
                candidates.extend(repo.by_sector_and_group(sector, kisi_grubu))

            if section.kategoriler:
                target_categories = set(section.kategoriler)
                candidates = [
                    c for c in candidates if target_categories & set(c.kategoriler)
                ]
            precise = candidates
            loose = candidates
        else:
            # Kanonik kisi grubu ile GEVSEK aday havuzu (tam-string varyantlarini da kapsar).
            target_kg = {
                canonicalizer.canonicalize(kg, "kisi_gruplari")
                for kg in section.kisi_gruplari
            }
            all_g = repo.by_sector_and_group(sector, None)
            loose = [
                c
                for c in all_g
                if canonicalizer.canonicalize(c.kisi_grubu, "kisi_gruplari") in target_kg
            ]

            # Kanonik kategori kesisimi ile HASSAS aday havuzu.
            if section.kategoriler:
                target_cat = {
                    canonicalizer.canonicalize(k, "kategoriler")
                    for k in section.kategoriler
                }
                precise = [
                    c
                    for c in loose
                    if target_cat
                    & {canonicalizer.canonicalize(k, "kategoriler") for k in c.kategoriler}
                ]
            else:
                precise = loose

        oneriler: dict[str, list[str]] = {}
        for fieldname in ENRICHABLE:
            existing = getattr(section, fieldname)
            additive = fieldname in ADDITIVE
            if existing and not additive:
                continue
            merged = _merge_dedup(*(getattr(c, fieldname) for c in precise))
            if not merged:
                # Hassas kesisim bos birakti; gevsek havuzdan doldur (uydurma yok, ham grounding).
                merged = _merge_dedup(*(getattr(c, fieldname) for c in loose))
            if merged and canonicalizer is not None:
                merged = canonicalizer.canonicalize_list(merged, fieldname)
            if additive and existing:
                # Additive: yalniz mevcut olmayanlari oner (ikisi de _merge_dedup ile NFC'li).
                merged = [m for m in merged if m not in set(existing)]
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
