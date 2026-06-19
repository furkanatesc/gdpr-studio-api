"""API entegrasyon testleri (httpx tabanlı TestClient).

Kapsam: HTTP katmanı — yönlendirme, durum kodları, sözleşme serileştirmesi, DB'ye
bağlı uçlar, CORS, bağımlılık çözümü. İş mantığı legal_core birim testlerinde (fake
provider) kapsandığı için burada gerçek model çağrısı yapılmaz (anahtarsız → 400 beklenir).
"""

from __future__ import annotations


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    body = r.json()
    assert body["service"] == "kvkk-yonetim-api"
    assert body["docs"] == "/docs"


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_db_ok(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ready"}


def test_categories_seedten_sirali_doner(client):
    r = client.get("/api/categories")
    assert r.status_code == 200
    cats = r.json()["categories"]
    assert cats == sorted(cats)  # uç sıralı döndürüyor
    assert {"Kimlik", "İletişim", "Sağlık Bilgileri"} <= set(cats)


def test_generate_anahtarsiz_400(client):
    # Geçerli gövde ama ne BYOK başlığı ne managed anahtar → net 400.
    r = client.post("/api/generate", json={"type": "aydinlatma", "fields": {}, "veriler": []})
    assert r.status_code == 400
    assert "API anahtarı yok" in r.json()["detail"]


def test_generate_gecersiz_tip_422(client):
    r = client.post("/api/generate", json={"type": "gecersiz_tur", "fields": {}, "veriler": []})
    assert r.status_code == 422


def test_generate_stream_anahtarsiz_400(client):
    r = client.post("/api/generate/stream", json={"type": "aydinlatma", "fields": {}, "veriler": []})
    assert r.status_code == 400
    assert "API anahtarı yok" in r.json()["detail"]


def test_cors_preflight_izinli_kaynak(client):
    r = client.options(
        "/api/categories",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert r.status_code == 200
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
