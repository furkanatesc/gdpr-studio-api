"""İhlal bildirimi — saf/deterministik değerlendirme (iki eşik + 72s)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from legal_core.grounding import OZEL_NITELIKLI
from legal_core.models import ClientProfile
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


def _naif(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


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
    saat = (_naif(simdi) - _naif(olay.tespit)).total_seconds() / 3600.0
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


def _kimlik_blok(profile: ClientProfile) -> str:
    return f"Veri Sorumlusu: {profile.unvan or profile.ad}\n"


def build_ihlal_kurul_prompt(
    olay: IhlalOlay,
    profile: ClientProfile,
    kategoriler: list[str],
    veri_turleri: list[str],
    measures: list[str],
    rules: list[str],
) -> str:
    tedbir = "\n".join(f"- {m}" for m in measures)
    kurallar = "\n".join(f"{i}. {r}" for i, r in enumerate(rules, 1))
    kat = ", ".join(kategoriler) or "(belirtilmemiş)"
    vt = ", ".join(veri_turleri) or "(belirtilmemiş)"
    return f"""Sen bir KVKK uzmanısın. Aşağıdaki veri ihlali olayı için Kişisel Verileri
Koruma Kurulu'na sunulacak resmi bir İHLAL BİLDİRİM FORMU taslağı hazırla. Resmi, teknik dil.

{_kimlik_blok(profile)}İhlal türü: {olay.tur}
İhlalin tespit tarihi: {olay.tespit:%d.%m.%Y %H:%M}
Etkilenen yaklaşık kişi sayısı: {olay.kisi_sayisi}
İhlalin nasıl gerçekleştiği: {olay.nasil}
Alınan/alınacak önlemler: {olay.onlemler}
Etkilenen veri kategorileri: {kat}
Etkilenen veri türleri: {vt}

Alınabilecek teknik/idari tedbir referansları:
{tedbir}

İş kuralları:
{kurallar}

BELGE İSKELETİ (AYNEN BU BAŞLIKLAR, bu sırayla):
1. VERİ SORUMLUSU BİLGİLERİ
2. İHLALİN TARİHİ VE TÜRÜ
3. ETKİLENEN KİŞİ GRUPLARI, VERİ KATEGORİLERİ VE TÜRLERİ
4. ETKİLENEN YAKLAŞIK KİŞİ SAYISI
5. İHLALİN NASIL GERÇEKLEŞTİĞİ
6. OLASI SONUÇLAR
7. ALINAN VE ALINACAK TEKNİK-İDARİ ÖNLEMLER
8. İRTİBAT NOKTASI
Bilinmeyen alanları "[Avukat tarafından doldurulacak]" bırak; uydurma.
"""


def build_ihlal_ilgili_kisi_prompt(
    olay: IhlalOlay,
    profile: ClientProfile,
    kategoriler: list[str],
) -> str:
    kat = ", ".join(kategoriler) or "(belirtilmemiş)"
    return f"""Sen bir KVKK uzmanısın. Aşağıdaki veri ihlali için İLGİLİ KİŞİLERE (etkilenen
vatandaşlara) gönderilecek SADE DİLDE bir bilgilendirme metni hazırla. Teknik jargon kullanma.

Veri sorumlusu: {profile.unvan or profile.ad}
İhlal türü: {olay.tur}
Etkilenen veri kategorileri: {kat}
Alınan önlemler: {olay.onlemler}

BELGE İSKELETİ (AYNEN, bu sırayla):
1. NE OLDU
2. HANGİ VERİLERİNİZ ETKİLENDİ
3. OLASI SONUÇLAR
4. SİZİN ALABİLECEĞİNİZ ÖNLEMLER
5. BİZE NASIL ULAŞABİLİRSİNİZ
Bilinmeyen alanları "[Avukat tarafından doldurulacak]" bırak.
"""
