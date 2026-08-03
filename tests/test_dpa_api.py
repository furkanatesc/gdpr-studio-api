from __future__ import annotations

import uuid


def _bootstrap_client(client_fresh, sector="saglik"):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    return client_fresh.post("/api/clients", json={"name": "Klinik A.S.", "sector": sector}).json()["id"]


def _put_inv(client_fresh, cid, rows):
    assert client_fresh.put(f"/api/clients/{cid}/inventory", json={"rows": rows}).status_code == 200


ROW = {"departman": "IK", "is_sureci": "Ozluk", "alt_surec": "Bordro", "kisi_grubu": "Calisan",
       "kategoriler": ["Sağlık Bilgileri"], "amaclar": ["Bordro"], "saklama_sureleri": ["10 yil"],
       "aktarim": ["Bulut"]}


def _create_processor(client_fresh, cid, aktarim_aliases=("Bulut",)):
    r = client_fresh.post(
        f"/api/clients/{cid}/processors",
        json={"ad": "Bulut", "unvan": "Bulut A.Ş.", "aktarimAliases": list(aktarim_aliases)},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_prepare_requires_auth(client_no_account):
    r = client_no_account.post(f"/api/clients/{uuid.uuid4()}/dpa/prepare",
                                json={"processorId": str(uuid.uuid4())})
    assert r.status_code in (401, 403)


def test_prepare_unknown_client_404(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    r = client_fresh.post(f"/api/clients/{uuid.uuid4()}/dpa/prepare",
                          json={"processorId": str(uuid.uuid4())})
    assert r.status_code == 404


def test_prepare_422_when_no_match(client_fresh):
    cid = _bootstrap_client(client_fresh)
    _put_inv(client_fresh, cid, [ROW])
    pid = _create_processor(client_fresh, cid, aktarim_aliases=("BaskaTedarikci",))
    r = client_fresh.post(f"/api/clients/{cid}/dpa/prepare", json={"processorId": pid})
    assert r.status_code == 422


def test_prepare_422_when_empty_inventory(client_fresh):
    cid = _bootstrap_client(client_fresh)
    pid = _create_processor(client_fresh, cid)
    r = client_fresh.post(f"/api/clients/{cid}/dpa/prepare", json={"processorId": pid})
    assert r.status_code == 422


def test_prepare_scope(client_fresh):
    cid = _bootstrap_client(client_fresh)
    pid = _create_processor(client_fresh, cid)
    _put_inv(client_fresh, cid, [ROW])
    r = client_fresh.post(f"/api/clients/{cid}/dpa/prepare", json={"processorId": pid})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["eslesenSurecSayisi"] >= 1
    assert isinstance(body["kategoriler"], list)


def test_generate_route_mounted(client_fresh):
    cid = _bootstrap_client(client_fresh)
    pid = _create_processor(client_fresh, cid)
    _put_inv(client_fresh, cid, [ROW])
    r = client_fresh.post(f"/api/clients/{cid}/dpa/generate", json={"processorId": pid})
    assert r.status_code != 404
