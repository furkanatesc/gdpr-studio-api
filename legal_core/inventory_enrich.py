"""Envanter (ProcessRecord) bos alanlari icin global grounding'den oneri toplar.

Saf, deterministik; oneriler InventorySuggestion.oneriler'dedir, kayit degerlerine
karismaz (onay web panelinde). aktarim/toplama icin grounding karsiligi yok -> asla
onerilmez; bos iseler elle_alanlar'da raporlanir. aydinlatma_enrich desenini izler
ama ProcessRecord uzerinde ve additive davranis YOK (amac doluluk).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from legal_core.aggregate_sections import _merge_dedup
from legal_core.canonical import Canonicalizer
from legal_core.models import ProcessRecord

ENRICHABLE = ["kategoriler", "veri_turleri", "amaclar", "hukuki_sebepler", "saklama_sureleri"]
ELLE_ALANLAR = ["aktarim"]


@dataclass(frozen=True)
class InventorySuggestion:
    index: int
    departman: str
    is_sureci: str
    alt_surec: str
    kisi_grubu: str
    oneriler: dict[str, list[str]] = field(default_factory=dict)
    elle_alanlar: list[str] = field(default_factory=list)


def enrich_inventory(
    records: list[ProcessRecord],
    sector: str,
    repo,
    canonicalizer: Canonicalizer | None = None,
) -> list[InventorySuggestion]:
    result: list[InventorySuggestion] = []
    for index, record in enumerate(records):
        if canonicalizer is None:
            loose = repo.by_sector_and_group(sector, record.kisi_grubu)
        else:
            target_kg = canonicalizer.canonicalize(record.kisi_grubu, "kisi_gruplari")
            loose = [
                c for c in repo.by_sector_and_group(sector, None)
                if canonicalizer.canonicalize(c.kisi_grubu, "kisi_gruplari") == target_kg
            ]

        if record.kategoriler:
            if canonicalizer is None:
                target_cat = set(record.kategoriler)
                precise = [c for c in loose if target_cat & set(c.kategoriler)]
            else:
                target_cat = {canonicalizer.canonicalize(k, "kategoriler") for k in record.kategoriler}
                precise = [
                    c for c in loose
                    if target_cat & {canonicalizer.canonicalize(k, "kategoriler") for k in c.kategoriler}
                ]
        else:
            precise = loose

        oneriler: dict[str, list[str]] = {}
        for fieldname in ENRICHABLE:
            if getattr(record, fieldname):
                continue
            merged = _merge_dedup(*(getattr(c, fieldname) for c in precise))
            if not merged:
                merged = _merge_dedup(*(getattr(c, fieldname) for c in loose))
            if merged and canonicalizer is not None:
                merged = canonicalizer.canonicalize_list(merged, fieldname)
            if merged:
                oneriler[fieldname] = merged

        elle = [f for f in ELLE_ALANLAR if not getattr(record, f)]

        if oneriler or elle:
            result.append(
                InventorySuggestion(
                    index=index,
                    departman=record.departman,
                    is_sureci=record.is_sureci,
                    alt_surec=record.alt_surec,
                    kisi_grubu=record.kisi_grubu,
                    oneriler=oneriler,
                    elle_alanlar=elle,
                )
            )
    return result
