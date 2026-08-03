"""DPA kapsam çözümü — saf/deterministik (DB'siz).

İşleyen ↔ envanter aktarım eşlemesi: bir süreç, aktarım değerlerinden herhangi biri
işleyenin alias'larıyla (norm eşleşme) eşleşiyorsa kapsama girer. Kapsam = eşleşen
süreçlerin kategori/veri türü/amaç/saklama/tedbir birleşimi (ilk görünen yazım korunur).
"""

from __future__ import annotations

from dataclasses import dataclass

from legal_core.models import ProcessRecord
from legal_core.normalize import norm


@dataclass(frozen=True)
class DpaScope:
    eslesen_surecler: list[ProcessRecord]
    kategoriler: list[str]
    veri_turleri: list[str]
    amaclar: list[str]
    saklama_sureleri: list[str]
    teknik_tedbirler: list[str]
    idari_tedbirler: list[str]


def _union(records: list[ProcessRecord], attr: str) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for r in records:
        for v in getattr(r, attr):
            if v and v.strip() and v not in seen:
                seen.add(v)
                out.append(v)
    return out


def resolve_dpa_scope(records: list[ProcessRecord], aliases: list[str]) -> DpaScope:
    alias_norms = {norm(a) for a in aliases if a and a.strip()}
    matched = [
        r for r in records
        if any(norm(a) in alias_norms for a in r.aktarim)
    ] if alias_norms else []
    return DpaScope(
        eslesen_surecler=matched,
        kategoriler=_union(matched, "kategoriler"),
        veri_turleri=_union(matched, "veri_turleri"),
        amaclar=_union(matched, "amaclar"),
        saklama_sureleri=_union(matched, "saklama_sureleri"),
        teknik_tedbirler=_union(matched, "teknik_tedbirler"),
        idari_tedbirler=_union(matched, "idari_tedbirler"),
    )


def distinct_aktarim_adlari(records: list[ProcessRecord]) -> list[str]:
    """Müvekkilin tüm süreçlerindeki farklı aktarım adları (norm ile dedupe, ilk yazım korunur)."""
    seen: set[str] = set()
    out: list[str] = []
    for r in records:
        for a in r.aktarim:
            if not a or not a.strip():
                continue
            n = norm(a)
            if n in seen:
                continue
            seen.add(n)
            out.append(a)
    return out
