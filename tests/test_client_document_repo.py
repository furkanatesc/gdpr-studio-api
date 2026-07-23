import uuid

from app.models import ClientDocument
from app.repositories import ClientDocumentRepository


def test_upsert_inserts_then_updates_same_key(db_session):
    org, cli = uuid.uuid4(), uuid.uuid4()
    repo = ClientDocumentRepository(db_session)
    a = repo.upsert(org, cli, "aydinlatma", "Calisan", "metin-1", 0.5, 0.8)
    db_session.flush()
    b = repo.upsert(org, cli, "aydinlatma", "Calisan", "metin-2", 0.9, None)
    db_session.flush()
    assert a.id == b.id  # ayni satir guncellendi
    rows = db_session.query(ClientDocument).filter_by(org_id=org, client_id=cli).all()
    assert len(rows) == 1
    assert rows[0].content == "metin-2" and rows[0].score_completeness == 0.9
    assert rows[0].score_compliance is None


def test_upsert_different_title_is_second_row(db_session):
    org, cli = uuid.uuid4(), uuid.uuid4()
    repo = ClientDocumentRepository(db_session)
    repo.upsert(org, cli, "aydinlatma", "Calisan", "m1", None, None)
    repo.upsert(org, cli, "aydinlatma", "Musteri", "m2", None, None)
    db_session.flush()
    assert len(repo.list_for_client(org, cli)) == 2


def test_get_returns_none_for_other_client(db_session):
    org, cli = uuid.uuid4(), uuid.uuid4()
    repo = ClientDocumentRepository(db_session)
    row = repo.upsert(org, cli, "aydinlatma", "Calisan", "m", None, None)
    db_session.flush()
    assert repo.get(org, cli, row.id) is not None
    assert repo.get(org, uuid.uuid4(), row.id) is None
