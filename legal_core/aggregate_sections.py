"""Sure toplayici: envanter kayitlarini hedef kisi gruplarina gore suzup
is_sureci bazinda bolumlere toplar. Saf, deterministik; AI/DB yok.

aktarim ve toplama alanlari ProcessRecord'dan (data JSONB'den turetilmis) merge+dedup
edilir; kanonik tablo olmadigindan canonicalize edilmez.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field

from legal_core.canonical import Canonicalizer
from legal_core.models import ProcessRecord


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip()


def _merge_dedup(*lists: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for lst in lists:
        for item in lst:
            value = _nfc(item)
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)
    return result


@dataclass(frozen=True)
class Section:
    is_sureci: str
    kisi_gruplari: list[str] = field(default_factory=list)
    kategoriler: list[str] = field(default_factory=list)
    veri_turleri: list[str] = field(default_factory=list)
    amaclar: list[str] = field(default_factory=list)
    hukuki_sebepler: list[str] = field(default_factory=list)
    saklama_sureleri: list[str] = field(default_factory=list)
    aktarim: list[str] = field(default_factory=list)
    toplama: list[str] = field(default_factory=list)


def aggregate_sections(
    records: list[ProcessRecord],
    target_groups: list[str],
    canonicalizer: Canonicalizer | None = None,
) -> list[Section]:
    targets = {_nfc(g) for g in target_groups if _nfc(g)}
    filtered = [r for r in records if _nfc(r.kisi_grubu) in targets]

    order: list[str] = []
    groups: dict[str, list[ProcessRecord]] = {}
    for record in filtered:
        key = _nfc(record.is_sureci)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(record)

    sections: list[Section] = []
    for key in order:
        group_records = groups[key]
        kategoriler = _merge_dedup(*(r.kategoriler for r in group_records))
        veri_turleri = _merge_dedup(*(r.veri_turleri for r in group_records))
        if canonicalizer is not None:
            kategoriler = canonicalizer.canonicalize_list(kategoriler, "kategoriler")
            veri_turleri = canonicalizer.canonicalize_list(veri_turleri, "veri_turleri")
        sections.append(
            Section(
                is_sureci=key,
                kisi_gruplari=_merge_dedup([r.kisi_grubu for r in group_records]),
                kategoriler=kategoriler,
                veri_turleri=veri_turleri,
                amaclar=_merge_dedup(*(r.amaclar for r in group_records)),
                hukuki_sebepler=_merge_dedup(*(r.hukuki_sebepler for r in group_records)),
                saklama_sureleri=_merge_dedup(*(r.saklama_sureleri for r in group_records)),
                aktarim=_merge_dedup(*(r.aktarim for r in group_records)),
                toplama=_merge_dedup(*(r.toplama for r in group_records)),
            )
        )
    return sections
