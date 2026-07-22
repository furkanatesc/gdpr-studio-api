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
    "evrakta yer alan 3. kişi": "Evrakta Yer Alan 3. Kişi",  # aynı grup, baş harf küçük yazılmış (1x)
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

# Cümleli alanlar: virgül CÜMLE-İÇİ noktalamadır, öğe ayracı değildir. split_cell
# virgülle de böler (token alanlar için doğru: "Ad, Soyad") — bu alanlarda kullanılırsa
# "5/2e Bir hakkın tesisi, kullanılması, korunması" anlamsız parçalara bölünür (PROGSA
# kıyas Bulgu 3). Bunlarda yalnız \n/; ayraçtır (extract_measures ile aynı gerekçe).
_NARRATIVE_FIELDS = frozenset({
    "amaclar", "hukuki_sebepler", "dayanaklar", "saklama_sureleri",
    "idari_tedbirler", "teknik_tedbirler",
})
_NARRATIVE_SPLIT = re.compile(r"[\n;]")


def _split_narrative(value: str) -> list[str]:
    if not value:
        return []
    return [p.strip() for p in _NARRATIVE_SPLIT.split(value) if p.strip()]


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
            field = _HEADER_MULTI[h]
            rec[field] = _split_narrative(val) if field in _NARRATIVE_FIELDS else split_cell(val)
    kg = canonical_kisi_grubu(rec.get("kisi_grubu", ""))
    if not kg:
        return None
    rec["kisi_grubu"] = kg
    return rec
