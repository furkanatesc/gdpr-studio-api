import uuid

from app.models import ClientDocument, ClientDocumentVersion


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
