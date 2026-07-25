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


def test_publish_wrong_client_404(client_fresh, db_session):
    boot = client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"}).json()
    cid_a = client_fresh.post("/api/clients", json={"name": "Muvekkil A"}).json()["id"]
    cid_b = client_fresh.post("/api/clients", json={"name": "Muvekkil B"}).json()["id"]
    ClientDocumentRepository(db_session).upsert(
        uuid.UUID(boot["orgId"]), uuid.UUID(cid_a), "aydinlatma", "Calisan", "taslak-metni", 0.5, 0.8
    )
    db_session.commit()
    doc_id = client_fresh.get(f"/api/clients/{cid_a}/documents").json()["documents"][0]["id"]
    r = client_fresh.post(
        f"/api/clients/{cid_b}/documents/{doc_id}/publish", json={"note": "capraz-muvekkil"}
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


def _seed_and_publish(client_fresh, db_session):
    boot = client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"}).json()
    cid = client_fresh.post("/api/clients", json={"name": "Muvekkil"}).json()["id"]
    ClientDocumentRepository(db_session).upsert(
        uuid.UUID(boot["orgId"]), uuid.UUID(cid), "aydinlatma", "Calisan", "surum-icerigi", 0.6, 0.7
    )
    db_session.commit()
    doc_id = client_fresh.get(f"/api/clients/{cid}/documents").json()["documents"][0]["id"]
    client_fresh.post(f"/api/clients/{cid}/documents/{doc_id}/publish", json={"note": "n1"})
    return cid, doc_id


def test_list_versions(client_fresh, db_session):
    cid, doc_id = _seed_and_publish(client_fresh, db_session)
    r = client_fresh.get(f"/api/clients/{cid}/documents/{doc_id}/versions")
    assert r.status_code == 200
    vers = r.json()["versions"]
    assert len(vers) == 1 and vers[0]["version"] == 1


def test_get_version_content_is_snapshot(client_fresh, db_session):
    cid, doc_id = _seed_and_publish(client_fresh, db_session)
    ver_id = client_fresh.get(f"/api/clients/{cid}/documents/{doc_id}/versions").json()["versions"][0]["id"]

    # yayindan sonra taslagi degistir: surumun hala YAYIN ANINDAKI icerigi donmesi lazim
    boot = client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro2"}).json()
    ClientDocumentRepository(db_session).upsert(
        uuid.UUID(boot["orgId"]), uuid.UUID(cid), "aydinlatma", "Calisan", "yeni-taslak-icerigi", 0.9, 0.9
    )
    db_session.commit()

    r = client_fresh.get(f"/api/clients/{cid}/documents/{doc_id}/versions/{ver_id}")
    assert r.status_code == 200
    assert r.json()["content"] == "surum-icerigi"


def test_documents_list_shows_latest_version(client_fresh, db_session):
    cid, doc_id = _seed_and_publish(client_fresh, db_session)
    docs = client_fresh.get(f"/api/clients/{cid}/documents").json()["documents"]
    row = next(d for d in docs if d["id"] == doc_id)
    assert row["latestVersion"] == 1
    assert row["latestPublishedAt"] is not None


def test_list_versions_wrong_client_404(client_fresh, db_session):
    boot = client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"}).json()
    cid_a = client_fresh.post("/api/clients", json={"name": "Muvekkil A"}).json()["id"]
    cid_b = client_fresh.post("/api/clients", json={"name": "Muvekkil B"}).json()["id"]
    ClientDocumentRepository(db_session).upsert(
        uuid.UUID(boot["orgId"]), uuid.UUID(cid_a), "aydinlatma", "Calisan", "surum-icerigi", 0.6, 0.7
    )
    db_session.commit()
    doc_id = client_fresh.get(f"/api/clients/{cid_a}/documents").json()["documents"][0]["id"]
    client_fresh.post(f"/api/clients/{cid_a}/documents/{doc_id}/publish", json={"note": "n1"})

    r = client_fresh.get(f"/api/clients/{cid_b}/documents/{doc_id}/versions")
    assert r.status_code == 404


def test_get_version_wrong_client_404(client_fresh, db_session):
    boot = client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"}).json()
    cid_a = client_fresh.post("/api/clients", json={"name": "Muvekkil A"}).json()["id"]
    cid_b = client_fresh.post("/api/clients", json={"name": "Muvekkil B"}).json()["id"]
    ClientDocumentRepository(db_session).upsert(
        uuid.UUID(boot["orgId"]), uuid.UUID(cid_a), "aydinlatma", "Calisan", "surum-icerigi", 0.6, 0.7
    )
    db_session.commit()
    doc_id = client_fresh.get(f"/api/clients/{cid_a}/documents").json()["documents"][0]["id"]
    client_fresh.post(f"/api/clients/{cid_a}/documents/{doc_id}/publish", json={"note": "n1"})
    ver_id = client_fresh.get(f"/api/clients/{cid_a}/documents/{doc_id}/versions").json()["versions"][0]["id"]

    r = client_fresh.get(f"/api/clients/{cid_b}/documents/{doc_id}/versions/{ver_id}")
    assert r.status_code == 404


def test_get_unknown_version_404(client_fresh, db_session):
    cid, doc_id = _seed_and_publish(client_fresh, db_session)
    r = client_fresh.get(f"/api/clients/{cid}/documents/{doc_id}/versions/{uuid.uuid4()}")
    assert r.status_code == 404


def test_list_documents_unpublished_shows_null_latest(client_fresh, db_session):
    cid, doc_id = _seed_draft(client_fresh, db_session)
    docs = client_fresh.get(f"/api/clients/{cid}/documents").json()["documents"]
    row = next(d for d in docs if d["id"] == doc_id)
    assert row["latestVersion"] is None


def test_version_docx_downloads(client_fresh, db_session):
    cid, doc_id = _seed_and_publish(client_fresh, db_session)
    ver_id = client_fresh.get(f"/api/clients/{cid}/documents/{doc_id}/versions").json()["versions"][0]["id"]
    r = client_fresh.get(f"/api/clients/{cid}/documents/versions/{ver_id}/docx")
    assert r.status_code == 200, r.text
    assert r.content[:2] == b"PK"  # docx = zip
    assert "attachment" in r.headers["content-disposition"]


def test_version_docx_wrong_client_404(client_fresh, db_session):
    boot = client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"}).json()
    cid_a = client_fresh.post("/api/clients", json={"name": "Muvekkil A"}).json()["id"]
    cid_b = client_fresh.post("/api/clients", json={"name": "Muvekkil B"}).json()["id"]
    ClientDocumentRepository(db_session).upsert(
        uuid.UUID(boot["orgId"]), uuid.UUID(cid_a), "aydinlatma", "Calisan", "surum-icerigi", 0.6, 0.7
    )
    db_session.commit()
    doc_id = client_fresh.get(f"/api/clients/{cid_a}/documents").json()["documents"][0]["id"]
    client_fresh.post(f"/api/clients/{cid_a}/documents/{doc_id}/publish", json={"note": "n1"})
    ver_id = client_fresh.get(f"/api/clients/{cid_a}/documents/{doc_id}/versions").json()["versions"][0]["id"]

    r = client_fresh.get(f"/api/clients/{cid_b}/documents/versions/{ver_id}/docx")
    assert r.status_code == 404
