import uuid

from app.repositories import ClientDocumentRepository
from tests.test_aydinlatma_api import _bootstrap_client  # desen paylasimi


def _seed_draft(client_fresh, db_session):
    """client_documents'a bir taslak koy (uretim akisini taklit etmeden, dogrudan repo).

    db_session, client_fresh'in get_session override'iyla aynı oturumdur (bkz. conftest.py).
    org_id, bootstrap yanıtından alınır (client_fresh gerçek DB kimlik çözümlemesi kullanır;
    IDENT sabiti yalnız endpoint fonksiyonlarının doğrudan çağrıldığı testlerde geçerlidir).
    """
    boot = client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"}).json()
    cid = client_fresh.post("/api/clients", json={"name": "Muvekkil"}).json()["id"]
    ClientDocumentRepository(db_session).upsert(
        uuid.UUID(boot["orgId"]), uuid.UUID(cid), "aydinlatma", "Calisan", "taslak-metni", 0.5, 0.8
    )
    db_session.commit()
    doc_id = client_fresh.get(f"/api/clients/{cid}/documents").json()["documents"][0]["id"]
    return cid, doc_id


def test_publish_creates_version_1(client_fresh, db_session):
    cid, doc_id = _seed_draft(client_fresh, db_session)
    r = client_fresh.post(
        f"/api/clients/{cid}/documents/{doc_id}/publish", json={"note": "ilk surum"}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["version"] == 1
    assert body["note"] == "ilk surum"


def test_publish_unknown_document_404(client_fresh):
    cid = _bootstrap_client(client_fresh)
    r = client_fresh.post(
        f"/api/clients/{cid}/documents/{uuid.uuid4()}/publish", json={"note": None}
    )
    assert r.status_code == 404


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
