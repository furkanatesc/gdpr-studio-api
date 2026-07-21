# tests/test_client_api.py
import io

from openpyxl import Workbook

from app.inventory_template import build_template_xlsx

_WORKBOOK_HEADER = [
    "No", "Bölüm", "Soru / Süreç", "Zorunlu?", "Cevap / Açıklama",
    "İşlenen Kişisel Veri", "İlgili Kişi Grubu", "Veri Kaynağı",
    "Kullanılan Sistem", "Veri Alıcısı", "Yurtdışı Aktarım",
    "Hukuki Sebep (KVKK → GDPR)", "Saklama Süresi", "Mevcut Doküman",
    "Kanıt Belgesi", "Risk / Not", "Sorumlu", "Durum",
]


def _build_survey_workbook() -> bytes:
    wb = Workbook()
    genel = wb.active
    genel.title = "01-Genel-Sirket"

    ik = wb.create_sheet("02-İnsan Kaynakları")
    ik.append(["Sayfa Başlığı"])
    ik.append(_WORKBOOK_HEADER)
    ik.append([
        1, "İşe Alım", "Özgeçmiş toplama", "Evet", "-",
        "Kimlik, İletişim", "Çalışan Adayı", "Kariyer Sitesi",
        "İK Sistemi", "", "Hayır",
        "Açık Rıza", "2 yıl", "-", "-", "-", "İK Md.", "Tamamlandı",
    ])
    ik.append([
        2, "Bordro", "Maaş ödemesi", "Evet", "-",
        "Kimlik, Banka Hesabı", "Çalışan", "Çalışandan",
        "Muhasebe Yazılımı", "Banka", "Evet",
        "Sözleşme", "10 yıl", "-", "-", "-", "Muhasebe Md.", "Tamamlandı",
    ])
    ik.append([
        3, "Genel", "Şirket kaç şubede faaliyet gösteriyor?", "Evet", "5",
        "", "", "", "", "", "",
        "", "", "-", "-", "-", "İK Md.", "Tamamlandı",
    ])
    ik.append([
        4, "İzin Takibi", "İzin talebi", "Hayır", "-",
        "Kimlik", "Çalışan", "Formdan", "-", "", "Hayır",
        "Sözleşme", "-", "-", "-", "-", "İK Md.", "Uygulanamaz",
    ])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_client_crud(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Büro"})
    r = client_fresh.post("/api/clients", json={"name": "Otel A.Ş.", "sector": "otel"})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    assert any(c["name"] == "Otel A.Ş." for c in client_fresh.get("/api/clients").json())
    assert client_fresh.patch(f"/api/clients/{cid}", json={"kep": "a@hs01.kep.tr"}).status_code == 200
    assert client_fresh.get(f"/api/clients/{cid}").json()["kep"] == "a@hs01.kep.tr"


def test_import_to_client(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Büro"})
    cid = client_fresh.post("/api/clients", json={"name": "Otel", "sector": "otel"}).json()["id"]
    content = build_template_xlsx()
    r = client_fresh.post(f"/api/clients/{cid}/inventory/import",
                          files={"file": ("e.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    assert "Çalışan" in r.json()["kisiGruplari"]
    assert "Çalışan" in client_fresh.get(f"/api/clients/{cid}/inventory/summary").json()["kisiGruplari"]


def test_grounding_options_endpoint(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Büro"})
    assert "Kimlik" in client_fresh.get("/api/grounding/options").json()["kategoriler"]


def test_patch_clears_explicit_null_but_keeps_omitted(client_fresh):
    """PATCH semantiği: acikca null gonderilen alan temizlenir, gonderilmeyen korunur."""
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Büro"})
    cid = client_fresh.post("/api/clients", json={"name": "Otel", "sector": "otel"}).json()["id"]
    client_fresh.patch(f"/api/clients/{cid}", json={"kep": "a@hs01.kep.tr", "mersis": "123"})

    client_fresh.patch(f"/api/clients/{cid}", json={"kep": None})
    body = client_fresh.get(f"/api/clients/{cid}").json()
    assert body["kep"] is None, "acikca null gonderilen alan temizlenmeli"
    assert body["mersis"] == "123", "gonderilmeyen alan korunmali"
    assert body["name"] == "Otel", "gonderilmeyen ad korunmali"


def test_inventory_get_and_put_roundtrip(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Büro"})
    cid = client_fresh.post("/api/clients", json={"name": "Otel", "sector": "otel"}).json()["id"]

    rows = [
        {"departman": "İK", "is_sureci": "Özlük", "alt_surec": "Bordro", "kisi_grubu": "Çalışan",
         "kategoriler": ["Kimlik", "Finans"], "amaclar": ["Bordro"], "saklama_sureleri": ["10 yıl"],
         "aktarim": ["SGK", "Yurt dışına aktarım"], "toplama": ["İlgili kişinin kendisi"]},
        {"departman": "Güvenlik", "is_sureci": "Kamera", "alt_surec": "Kayıt", "kisi_grubu": "Ziyaretçi",
         "kategoriler": ["Görsel Ve İşitsel Kayıtlar"]},
    ]
    r = client_fresh.put(f"/api/clients/{cid}/inventory", json={"rows": rows})
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 2

    got = client_fresh.get(f"/api/clients/{cid}/inventory").json()["rows"]
    assert len(got) == 2
    ik = next(x for x in got if x["kisi_grubu"] == "Çalışan")
    assert ik["kategoriler"] == ["Kimlik", "Finans"]
    assert ik["saklama_sureleri"] == ["10 yıl"]
    assert ik["aktarim"] == ["SGK", "Yurt dışına aktarım"]
    assert ik["toplama"] == ["İlgili kişinin kendisi"]

    # elle düzenleme: bir satır sil, birine kategori ekle → PUT replace
    got[0]["kategoriler"] = got[0]["kategoriler"] + ["İletişim"]
    r2 = client_fresh.put(f"/api/clients/{cid}/inventory", json={"rows": [got[0]]})
    assert r2.json()["count"] == 1
    again = client_fresh.get(f"/api/clients/{cid}/inventory").json()["rows"]
    assert len(again) == 1


def test_inventory_put_bos_kisi_grubu_reddedilir(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Büro"})
    cid = client_fresh.post("/api/clients", json={"name": "Otel", "sector": "otel"}).json()["id"]
    r = client_fresh.put(f"/api/clients/{cid}/inventory",
                         json={"rows": [{"departman": "İK", "kisi_grubu": ""}]})
    assert r.status_code == 422, "kişi grubu zorunlu (sorgu ekseni)"


def test_import_workbook_to_client(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Büro"})
    cid = client_fresh.post("/api/clients", json={"name": "Otel", "sector": "otel"}).json()["id"]
    content = _build_survey_workbook()
    r = client_fresh.post(f"/api/clients/{cid}/inventory/import-workbook",
                          files={"file": ("anket.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 2, "teşhis satırı ve Uygulanamaz satırı atlanmalı"
    assert sorted(body["kisiGruplari"]) == ["Çalışan", "Çalışan Adayı"]

    rows = client_fresh.get(f"/api/clients/{cid}/inventory").json()["rows"]
    bordro = next(x for x in rows if x["kisi_grubu"] == "Çalışan")
    assert "Banka" in bordro["aktarim"]
    assert "Yurt dışına aktarım" in bordro["aktarim"]
    assert bordro["toplama"] == ["Çalışandan"]


def test_import_workbook_olmayan_client_404(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Büro"})
    content = _build_survey_workbook()
    r = client_fresh.post("/api/clients/00000000-0000-0000-0000-000000000000/inventory/import-workbook",
                          files={"file": ("anket.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 404


def test_import_workbook_gecersiz_dosya_422(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Büro"})
    cid = client_fresh.post("/api/clients", json={"name": "Otel", "sector": "otel"}).json()["id"]
    r = client_fresh.post(f"/api/clients/{cid}/inventory/import-workbook",
                          files={"file": ("e.xlsx", b"notxlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 422
