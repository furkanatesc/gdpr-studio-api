from __future__ import annotations

import uuid


def _bootstrap_client(client_fresh, sector="saglik"):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    return client_fresh.post("/api/clients", json={"name": "Klinik A.S.", "sector": sector}).json()["id"]


def _put_inv(client_fresh, cid, rows):
    assert client_fresh.put(f"/api/clients/{cid}/inventory", json={"rows": rows}).status_code == 200


ROW = {"departman": "IK", "is_sureci": "Ozluk", "alt_surec": "Bordro", "kisi_grubu": "Calisan",
       "kategoriler": ["Sağlık Bilgileri"], "amaclar": ["Bordro"], "saklama_sureleri": ["10 yil"]}


def test_prepare_requires_auth(client_no_account):
    r = client_no_account.post(f"/api/clients/{uuid.uuid4()}/dpia/prepare",
                               json={"anket": {"buyukOlcek": False, "yeniTeknoloji": False,
                                               "savunmasizGrup": False, "veriEslestirme": False}})
    assert r.status_code in (401, 403)


def test_prepare_unknown_client_404(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    r = client_fresh.post(f"/api/clients/{uuid.uuid4()}/dpia/prepare",
                          json={"anket": {"buyukOlcek": False, "yeniTeknoloji": False,
                                          "savunmasizGrup": False, "veriEslestirme": False}})
    assert r.status_code == 404


def test_prepare_empty_inventory_422(client_fresh):
    cid = _bootstrap_client(client_fresh)
    r = client_fresh.post(f"/api/clients/{cid}/dpia/prepare",
                          json={"anket": {"buyukOlcek": False, "yeniTeknoloji": False,
                                          "savunmasizGrup": False, "veriEslestirme": False}})
    assert r.status_code == 422


def test_prepare_verdict_ozel_nitelikli_plus_anket(client_fresh):
    cid = _bootstrap_client(client_fresh)
    _put_inv(client_fresh, cid, [ROW])  # Sağlık = özel nitelikli (auto)
    r = client_fresh.post(f"/api/clients/{cid}/dpia/prepare",
                          json={"anket": {"buyukOlcek": False, "yeniTeknoloji": False,
                                          "savunmasizGrup": True, "veriEslestirme": False}})
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["otomatik"]["ozelNitelikliVar"] is True
    assert b["kriterSayisi"] == 2
    assert b["zorunlu"] is True


def test_generate_route_mounted(client_fresh):
    cid = _bootstrap_client(client_fresh)
    _put_inv(client_fresh, cid, [ROW])
    # API key yok/dev-bypass: en azindan 422/erisim degil, akis baslar veya kota/By key hatasi
    r = client_fresh.post(f"/api/clients/{cid}/dpia/generate", json={"tetiklenenler": ["ozel_nitelikli"]})
    assert r.status_code != 404  # mount dogrulamasi (kayit test deseni)
