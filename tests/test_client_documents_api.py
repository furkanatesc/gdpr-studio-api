import uuid

from tests.test_aydinlatma_api import _bootstrap_client  # desen paylasimi


def test_list_bos_muvekkil_bos_liste(client_fresh):
    cid = _bootstrap_client(client_fresh)
    r = client_fresh.get(f"/api/clients/{cid}/documents")
    assert r.status_code == 200
    assert r.json()["documents"] == []


def test_list_baska_org_muvekkili_404(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    r = client_fresh.get(f"/api/clients/{uuid.uuid4()}/documents")
    assert r.status_code == 404


def test_get_bilinmeyen_belge_404(client_fresh):
    cid = _bootstrap_client(client_fresh)
    r = client_fresh.get(f"/api/clients/{cid}/documents/{uuid.uuid4()}")
    assert r.status_code == 404
