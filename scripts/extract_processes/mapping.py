"""Envanter satırı → süreç kaydı eşlemesi (26 sütun) + kişi grubu kanonikleştirme."""

from __future__ import annotations

import re
import unicodedata

from scripts.enrich_categories.mapping import split_cell

# Envanter başlığı → süreç kaydı alanı. Tekil (str) alanlar:
_SINGLE = {
    "Departman": "departman",
    "Departman Kodu": "departman_kodu",
    "İş Süreci": "is_sureci",
    "Alt Süreç": "alt_surec",
    "Veri Konusu Kişi Grubu": "kisi_grubu",
    "Rol": "rol",
    "Veri Kayıt Sistemi": "veri_kayit_sistemi",
    "Kaynak (Elde Etme)": "kaynak",
    "Yurtdışına Aktarım Yapılıyor Mu?": "yurtdisi_aktarim",
    "Alıcı Niteliği (VS-Vİ) (Aktarım)": "alici_niteligi",
    "Veri Aktarım Metodu": "aktarim_metodu",
    "Ülke (Aktarım)": "ulke",
    "Açıklama": "aciklama",
}
# Çok-değerli (list[str]) alanlar:
_MULTI = {
    "Kişisel Veri Kategorisi": "kategoriler",
    "Veri Türü": "veri_turleri",
    "İşlem": "islem",
    "Veri Aktarım Alıcı Grubu": "alici_grubu",
    "Alıcı (Aktarım)": "alici",
    "Veri Kullanım Amacı": "amaclar",
    "Hukuki Sebep": "hukuki_sebepler",
    "Dayanak": "dayanaklar",
    "Azami Süre (Saklama)": "saklama_sureleri",
    "Ortam Format": "ortam_format",
    "Konum": "konum",
    "İdari Güvenlik Tedbiri": "idari_tedbirler",
    "Teknik Güvenlik Tedbiri": "teknik_tedbirler",
}

PROCESS_KEY_COLUMNS = ("departman", "is_sureci", "alt_surec", "kisi_grubu")

# Dosya adı deseni (küçük harf, NFC) → sektör kodu.
SECTOR_BY_FILENAME = {
    "diş klini": "dis_klinigi",
    "e-ticaret": "e_ticaret",
    "otel": "otel",
    "psikoloji": "psikoloji",
    "progsa": "meslek_orgutu",   # anonimleştirme: gerçek kurum adı taşınmaz
    "şirket": "sirket",
}

# Kaynak veride AYNI grubun iki yazımı ölçüldü → açık, gözden geçirilmiş eşleme
# (TAG_SYNONYMS deseni). Uydurma değil; yeni hata çıkarsa buraya eklenir.
_KISI_GRUBU_ALIASES = {
    "tederikçi yetkilisi": "Tedarikçi Yetkilisi",  # 8x
}
# Kişi grubu OLMAYAN, veride kalmış çöp (1x).
_KISI_GRUBU_JUNK = {"organizasyon şirket fiyat teklifi"}
_JUNK = {"", "???", "??", "-", "--", "n/a", "na", "bilinmiyor", "belirsiz", "yok"}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s).strip())


def _hnorm(s: str) -> str:
    # Python'ın varsayılan .lower() metodu Türkçe büyük "İ"yi bileşik nokta içeren
    # "i" + U+0307'ye çevirir (yerel/ASCII "i" değil). Sektör deseni eşlemesi düz
    # ASCII/Türkçe küçük harfle yazıldığından, İ/I harflerini Türkçe kurala göre
    # önce katlayıp sonra .lower() çağırıyoruz.
    n = _norm(s).replace("İ", "i").replace("I", "ı")
    return n.lower()


_HEADER_SINGLE = {_hnorm(k): v for k, v in _SINGLE.items()}
_HEADER_MULTI = {_hnorm(k): v for k, v in _MULTI.items()}


def sector_for_filename(name: str) -> str | None:
    low = _hnorm(name)
    for pattern, code in SECTOR_BY_FILENAME.items():
        if pattern in low:
            return code
    return None


def canonical_kisi_grubu(raw: str) -> str | None:
    n = _norm(raw)
    key = _hnorm(raw)  # Türkçe İ/I katlama dahil; _JUNK/_KISI_GRUBU_ALIASES ile tutarlı
    if key in _JUNK or key in _KISI_GRUBU_JUNK:
        return None
    return _KISI_GRUBU_ALIASES.get(key, n)


def row_to_process(header_row: list[str], cells: list[str]) -> dict | None:
    """Satırı süreç kaydına çevirir. Kişi grubu yoksa/çöpse None (sorgu ekseni zorunlu)."""
    rec: dict = {}
    for i, head in enumerate(header_row):
        if i >= len(cells):
            continue
        h = _hnorm(head)
        val = cells[i]
        if h in _HEADER_SINGLE:
            rec[_HEADER_SINGLE[h]] = _norm(val)
        elif h in _HEADER_MULTI:
            rec[_HEADER_MULTI[h]] = split_cell(val)
    kg = canonical_kisi_grubu(rec.get("kisi_grubu", ""))
    if not kg:
        return None
    rec["kisi_grubu"] = kg
    return rec
