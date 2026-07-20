# tests/test_client_api.py
from app.inventory_template import build_template_xlsx


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
