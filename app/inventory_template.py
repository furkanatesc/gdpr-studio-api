"""Boş KVKK envanter şablonu (indirilebilir xlsx)."""

from __future__ import annotations

import io

from openpyxl import Workbook

STANDARD_HEADERS = [
    "Departman", "Departman Kodu", "İş Süreci", "Alt Süreç", "Veri Konusu Kişi Grubu",
    "Rol", "Veri Kayıt Sistemi", "Kişisel Veri Kategorisi", "Veri Türü", "İşlem",
    "Kaynak (Elde Etme)", "Yurtdışına Aktarım Yapılıyor Mu?", "Veri Aktarım Alıcı Grubu",
    "Alıcı (Aktarım)", "Alıcı Niteliği (VS-Vİ) (Aktarım)", "Veri Aktarım Metodu",
    "Ülke (Aktarım)", "Veri Kullanım Amacı", "Hukuki Sebep", "Dayanak",
    "Azami Süre (Saklama)", "Ortam Format", "Konum", "İdari Güvenlik Tedbiri",
    "Teknik Güvenlik Tedbiri", "Açıklama",
]

_ORNEK = ["İK", "İK-1001", "İşe Giriş", "Kimlik Teyidi", "Çalışan", "", "", "Kimlik", "Ad Soyad",
          "Elde Etme", "İlgili Kişinin Beyanı", "Hayır", "", "", "", "", "", "İş sözleşmesinin ifası",
          "5/2c Sözleşmenin Kurulması veya İfası", "4857 sayılı Kanun", "İş ilişkisi + 10 yıl", "Kağıt", "", "", "", ""]


def build_template_xlsx() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Envanter"
    ws.append(STANDARD_HEADERS)
    ws.append(_ORNEK)
    voc = wb.create_sheet("Sözlük")
    voc.append(["İşlem", "Hukuki Sebep (örnek)"])
    for row in zip(
        ["Elde Etme", "Aktarma", "Saklama", "Üretme", "Silme"],
        ["5/1 Açık Rıza", "5/2a Kanunlarda Açıkça Öngörülmesi", "5/2c Sözleşmenin İfası",
         "5/2ç Hukuki Yükümlülük", "5/2f Meşru Menfaat"],
        strict=True,
    ):
        voc.append(list(row))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
