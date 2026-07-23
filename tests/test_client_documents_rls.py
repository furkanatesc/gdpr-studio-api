"""client_documents iki-org RLS izolasyon testi (FORCE RLS, kvkk_app non-superuser)."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text

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
