"""DPIA zorunluluk testi — saf/deterministik (envanterden otomatik + anket)."""

from __future__ import annotations

from dataclasses import dataclass, field

from legal_core.grounding import OZEL_NITELIKLI
from legal_core.models import ProcessRecord
from legal_core.normalize import norm

_OZEL_NORM = {norm(k) for k in OZEL_NITELIKLI}
_PROFIL_SINYAL = ("profil", "otomatik karar", "skorlama")


@dataclass(frozen=True)
class DpiaAnket:
    buyuk_olcek: bool = False
    yeni_teknoloji: bool = False
    savunmasiz_grup: bool = False
    veri_eslestirme: bool = False


@dataclass(frozen=True)
class DpiaVerdict:
    ozel_nitelikli_var: bool
    profilleme_var: bool
    kriter_sayisi: int
    zorunlu: bool
    tetiklenenler: list[str] = field(default_factory=list)


def _has_ozel_nitelikli(records: list[ProcessRecord]) -> bool:
    for r in records:
        for k in r.kategoriler:
            if norm(k) in _OZEL_NORM:
                return True
    return False


def _has_profilleme(records: list[ProcessRecord]) -> bool:
    for r in records:
        for i in r.islem:
            n = norm(i)
            if any(s in n for s in _PROFIL_SINYAL):
                return True
    return False


def evaluate_dpia_necessity(records: list[ProcessRecord], anket: DpiaAnket) -> DpiaVerdict:
    ozel = _has_ozel_nitelikli(records)
    profil = _has_profilleme(records)
    flags = {
        "ozel_nitelikli": ozel,
        "profilleme": profil,
        "buyuk_olcek": anket.buyuk_olcek,
        "yeni_teknoloji": anket.yeni_teknoloji,
        "savunmasiz_grup": anket.savunmasiz_grup,
        "veri_eslestirme": anket.veri_eslestirme,
    }
    tetiklenenler = [k for k, v in flags.items() if v]
    return DpiaVerdict(
        ozel_nitelikli_var=ozel,
        profilleme_var=profil,
        kriter_sayisi=len(tetiklenenler),
        zorunlu=len(tetiklenenler) >= 2,
        tetiklenenler=tetiklenenler,
    )
