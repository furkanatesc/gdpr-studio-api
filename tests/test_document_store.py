import uuid

from app.models import ClientDocument
from app.modules.document_store import store_client_document


def test_store_client_document_yazar_ve_puan_b_hesaplar(db_session):
    org, cli = uuid.uuid4(), uuid.uuid4()
    store_client_document(db_session, org, cli, "cerez", "site.com", "metin", 0.75)
    rows = db_session.query(ClientDocument).filter_by(org_id=org, client_id=cli).all()
    assert len(rows) == 1
    assert rows[0].doc_type == "cerez"
    assert rows[0].title == "site.com"
    assert rows[0].score_completeness == 0.75
    # org'da hic compliance_status yok -> cerez icin 0/3 = 0.0 (None degil)
    assert rows[0].score_compliance == 0.0
