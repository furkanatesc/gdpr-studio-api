"""İhlal bildirimi — saf/deterministik değerlendirme (iki eşik + 72s)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from legal_core.grounding import OZEL_NITELIKLI
from legal_core.normalize import norm

BUYUK_OLCEK_ESIGI = 1000
_OZEL_NORM = {norm(k) for k in OZEL_NITELIKLI}


@dataclass(frozen=True)
class IhlalOlay:
    tespit: datetime
    tur: str
    etkilenen_kategoriler: list[str]
    ozel_nitelikli_secili: bool
    kimlik_finansal: bool
    sifreli: bool
    kisi_sayisi: int
    nasil: str
    onlemler: str


@dataclass(frozen=True)
class IhlalVerdict:
    kurul_gerekli: bool
    ilgili_kisi_gerekli: bool
    ilgili_kisi_muafiyet: bool
    ilgili_kisi_sinyaller: list[str]
    ozel_nitelikli_var: bool
    saat_kalan: float | None
    sure_asildi: bool


def _ozel_nitelikli(olay: IhlalOlay) -> bool:
    if olay.ozel_nitelikli_secili:
        return True
    return any(norm(k) in _OZEL_NORM for k in olay.etkilenen_kategoriler)


def evaluate_ihlal_bildirim(olay: IhlalOlay, *, simdi: datetime) -> IhlalVerdict:
    ozel = _ozel_nitelikli(olay)
    sinyaller: list[str] = []
    if ozel:
        sinyaller.append("ozel_nitelikli")
    if olay.kimlik_finansal:
        sinyaller.append("kimlik_finansal")
    if olay.kisi_sayisi >= BUYUK_OLCEK_ESIGI:
        sinyaller.append("buyuk_olcek")
    if not olay.sifreli:
        sinyaller.append("sifresiz")

    muafiyet = olay.sifreli
    ilgili_gerekli = bool(sinyaller) and not muafiyet
    saat = (simdi - olay.tespit).total_seconds() / 3600.0
    saat_kalan = 72.0 - saat
    return IhlalVerdict(
        kurul_gerekli=True,
        ilgili_kisi_gerekli=ilgili_gerekli,
        ilgili_kisi_muafiyet=muafiyet,
        ilgili_kisi_sinyaller=sinyaller,
        ozel_nitelikli_var=ozel,
        saat_kalan=saat_kalan,
        sure_asildi=saat_kalan < 0,
    )
