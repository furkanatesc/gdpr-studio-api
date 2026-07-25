import uuid

from app.models import ClientDocument, ClientDocumentVersion
from app.repositories import ClientDocumentRepository, ClientDocumentVersionRepository


def test_version_row_persists(db_session):
    org, cli = uuid.uuid4(), uuid.uuid4()
    doc = ClientDocument(
        org_id=org, client_id=cli, doc_type="aydinlatma", title="Calisan", content="taslak"
    )
    db_session.add(doc)
    db_session.flush()
    ver = ClientDocumentVersion(
        document_id=doc.id, org_id=org, version=1, content="taslak",
        score_completeness=0.5, score_compliance=0.8, note="ilk", published_by=uuid.uuid4(),
    )
    db_session.add(ver)
    db_session.flush()
    assert ver.id is not None
    assert ver.published_at is not None


def _draft(db_session, org, cli, title="Calisan", content="taslak"):
    return ClientDocumentRepository(db_session).upsert(
        org, cli, "aydinlatma", title, content, 0.5, 0.8
    )


def test_publish_increments_version_and_snapshots(db_session):
    org, cli = uuid.uuid4(), uuid.uuid4()
    doc = _draft(db_session, org, cli, content="v-metni-1")
    db_session.flush()
    repo = ClientDocumentVersionRepository(db_session)
    v1 = repo.publish(org, doc.id, "v-metni-1", 0.5, 0.8, "ilk", None)
    db_session.flush()
    v2 = repo.publish(org, doc.id, "v-metni-2", 0.9, 1.0, None, None)
    db_session.flush()
    assert (v1.version, v2.version) == (1, 2)
    assert v1.content == "v-metni-1" and v2.content == "v-metni-2"
    assert v1.note == "ilk" and v2.note is None


def test_list_for_document_desc(db_session):
    org, cli = uuid.uuid4(), uuid.uuid4()
    doc = _draft(db_session, org, cli)
    db_session.flush()
    repo = ClientDocumentVersionRepository(db_session)
    repo.publish(org, doc.id, "a", None, None, None, None)
    repo.publish(org, doc.id, "b", None, None, None, None)
    db_session.flush()
    vers = repo.list_for_document(org, doc.id)
    assert [v.version for v in vers] == [2, 1]


def test_get_version_scoped(db_session):
    org, cli = uuid.uuid4(), uuid.uuid4()
    doc = _draft(db_session, org, cli)
    db_session.flush()
    repo = ClientDocumentVersionRepository(db_session)
    v = repo.publish(org, doc.id, "a", None, None, None, None)
    db_session.flush()
    assert repo.get_version(org, doc.id, v.id) is not None
    assert repo.get_version(uuid.uuid4(), doc.id, v.id) is None


def test_latest_versions_for_client(db_session):
    org, cli = uuid.uuid4(), uuid.uuid4()
    d1 = _draft(db_session, org, cli, title="Calisan")
    d2 = _draft(db_session, org, cli, title="Musteri")
    db_session.flush()
    repo = ClientDocumentVersionRepository(db_session)
    repo.publish(org, d1.id, "a", None, None, None, None)
    repo.publish(org, d1.id, "b", None, None, None, None)
    db_session.flush()
    latest = repo.latest_versions_for_client(org, cli)
    assert latest[d1.id][0] == 2
    assert d2.id not in latest
