"""client_documents iki-org RLS izolasyon testi (FORCE RLS, kvkk_app non-superuser)."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DB_URL = os.getenv("RLS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="RLS yalniz Postgres'te; RLS_TEST_DATABASE_URL gerekli")


def _assert_non_superuser(conn) -> None:
    is_super = conn.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar()
    assert not is_super, "RLS testleri kvkk_app (non-superuser) ile kosmali."


def _count(conn, org_ids) -> int:
    return conn.execute(
        text("SELECT count(*) FROM client_documents WHERE org_id = ANY(:oids)"),
        {"oids": [str(o) for o in org_ids]},
    ).scalar()


def test_client_documents_rls_isolates_orgs_and_bypass_sees_all():
    eng = create_engine(DB_URL, future=True)
    org_a, org_b, cli_a, cli_b = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    conn = eng.connect()
    trans = conn.begin()
    try:
        _assert_non_superuser(conn)
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        for oid, name in [(org_a, "Doc A"), (org_b, "Doc B")]:
            conn.execute(text("INSERT INTO organizations (id, name) VALUES (:id, :n)"), {"id": oid, "n": name})
        for oid, cid in [(org_a, cli_a), (org_b, cli_b)]:
            conn.execute(
                text("INSERT INTO clients (id, org_id, name) VALUES (:id, :o, 'C')"), {"id": cid, "o": oid}
            )
            conn.execute(
                text(
                    "INSERT INTO client_documents (id, org_id, client_id, doc_type, title, content) "
                    "VALUES (:id, :o, :c, 'aydinlatma', 'Calisan', 'metin')"
                ),
                {"id": uuid.uuid4(), "o": oid, "c": cid},
            )
        conn.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        conn.execute(text("SELECT set_config('app.current_org_id', :o, true)"), {"o": str(org_a)})
        assert _count(conn, [org_a, org_b]) == 1  # B gizli
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        assert _count(conn, [org_a, org_b]) == 2
    finally:
        trans.rollback()
        conn.close()
        eng.dispose()


def test_client_documents_fail_closed_without_guc():
    eng = create_engine(DB_URL, future=True)
    conn = eng.connect()
    trans = conn.begin()
    try:
        _assert_non_superuser(conn)
        assert conn.execute(text("SELECT count(*) FROM client_documents")).scalar() == 0
    finally:
        trans.rollback()
        conn.close()
        eng.dispose()


def test_store_generated_document_reestablishes_rls_context_after_commit():
    """C1 regresyonu: reserve/settle_generation_usage `commit()` yapar, bu da
    `app.current_org_id` GUC'sini (transaction-local) sıfırlar. `_store_generated_document`
    kendi başında org bağlamını yeniden kurmazsa: statuses_for_org boş döner (Puan B = 0.0)
    VE client_documents INSERT'i RLS WITH CHECK ihlaliyle patlar (best-effort yutar,
    belge hiç saklanmaz). Bu test GUC'siz (commit-sonrası) durumdan başlayıp fonksiyonun
    kendi kendini toparladığını doğrular.

    _store_generated_document kendi session.commit()'ini yapar; bu yüzden burada dış bir
    transaction+rollback yerine üç ayrı adım (kurulum / çağrı / doğrulama+temizlik) kullanılır
    ve en sonda satırlar elle silinir.
    """
    from app.modules.aydinlatma import _store_generated_document
    from legal_core.aggregate_sections import Section

    eng = create_engine(DB_URL, future=True)
    org_id, client_id = uuid.uuid4(), uuid.uuid4()
    try:
        with eng.begin() as conn:
            _assert_non_superuser(conn)
            conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
            conn.execute(
                text("INSERT INTO organizations (id, name) VALUES (:id, 'RLS Store Org')"),
                {"id": str(org_id)},
            )
            conn.execute(
                text("INSERT INTO clients (id, org_id, name) VALUES (:id, :o, 'C')"),
                {"id": str(client_id), "o": str(org_id)},
            )
            conn.execute(
                text(
                    "INSERT INTO compliance_status (id, org_id, requirement_key, status, source) "
                    "VALUES (:id, :o, 'aydinlatma_metni', 'yapildi', 'user')"
                ),
                {"id": str(uuid.uuid4()), "o": str(org_id)},
            )
            # Blok commit'te biter: bypass_rls + current_org_id transaction-local oldugu
            # icin bir SONRAKI baglanti/oturumda ikisi de bastan UNSET (fail-closed) olur —
            # bu, reserve/settle_generation_usage'in commit'inden SONRAKI durumu simule eder.

        conn = eng.connect()
        session = sessionmaker(bind=conn, future=True)()
        try:
            section = Section(is_sureci="Test sureci", kisi_gruplari=["calisan"])
            _store_generated_document(session, org_id, client_id, [section], "test metni")
        finally:
            session.close()
            conn.close()

        try:
            with eng.begin() as conn:
                conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
                row = conn.execute(
                    text(
                        "SELECT score_compliance FROM client_documents "
                        "WHERE org_id = :o AND client_id = :c AND doc_type = 'aydinlatma'"
                    ),
                    {"o": str(org_id), "c": str(client_id)},
                ).fetchone()
                assert row is not None, (
                    "C1 regresyonu: belge saklanmadi (org GUC'si yeniden kurulmamis olabilir)"
                )
                assert row[0] is not None and row[0] > 0, (
                    "Puan B sifir: statuses_for_org bos donmus (org GUC'si eksik)"
                )
        finally:
            with eng.begin() as conn:
                conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
                conn.execute(text("DELETE FROM client_documents WHERE org_id = :o"), {"o": str(org_id)})
                conn.execute(text("DELETE FROM compliance_status WHERE org_id = :o"), {"o": str(org_id)})
                conn.execute(text("DELETE FROM clients WHERE org_id = :o"), {"o": str(org_id)})
                conn.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": str(org_id)})
    finally:
        eng.dispose()
