"""client_document_versions iki-org RLS + degismezlik (kvkk_app UPDATE/DELETE yok)."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text

DB_URL = os.getenv("RLS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="RLS yalniz Postgres'te; RLS_TEST_DATABASE_URL gerekli")


def _assert_non_superuser(conn) -> None:
    is_super = conn.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar()
    assert not is_super, "RLS testleri kvkk_app (non-superuser) ile kosmali."


def _seed(conn, org, cli, doc, ver):
    conn.execute(text("INSERT INTO organizations (id, name) VALUES (:id, 'O')"), {"id": str(org)})
    conn.execute(text("INSERT INTO clients (id, org_id, name) VALUES (:id, :o, 'C')"), {"id": str(cli), "o": str(org)})
    conn.execute(
        text(
            "INSERT INTO client_documents (id, org_id, client_id, doc_type, title, content) "
            "VALUES (:id, :o, :c, 'aydinlatma', 'Calisan', 'taslak')"
        ),
        {"id": str(doc), "o": str(org), "c": str(cli)},
    )
    conn.execute(
        text(
            "INSERT INTO client_document_versions (id, document_id, org_id, version, content) "
            "VALUES (:id, :d, :o, 1, 'surum')"
        ),
        {"id": str(ver), "d": str(doc), "o": str(org)},
    )


def test_versions_rls_isolates_orgs():
    eng = create_engine(DB_URL, future=True)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    cli_a, cli_b = uuid.uuid4(), uuid.uuid4()
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    ver_a, ver_b = uuid.uuid4(), uuid.uuid4()
    conn = eng.connect()
    trans = conn.begin()
    try:
        _assert_non_superuser(conn)
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        _seed(conn, org_a, cli_a, doc_a, ver_a)
        _seed(conn, org_b, cli_b, doc_b, ver_b)
        conn.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        conn.execute(text("SELECT set_config('app.current_org_id', :o, true)"), {"o": str(org_a)})
        cnt = conn.execute(
            text("SELECT count(*) FROM client_document_versions WHERE org_id = ANY(:oids)"),
            {"oids": [str(org_a), str(org_b)]},
        ).scalar()
        assert cnt == 1  # B gizli
    finally:
        trans.rollback()
        conn.close()
        eng.dispose()


def test_versions_fail_closed_without_guc():
    eng = create_engine(DB_URL, future=True)
    conn = eng.connect()
    trans = conn.begin()
    try:
        _assert_non_superuser(conn)
        assert conn.execute(text("SELECT count(*) FROM client_document_versions")).scalar() == 0
    finally:
        trans.rollback()
        conn.close()
        eng.dispose()


def test_versions_immutable_no_update_delete_grant():
    eng = create_engine(DB_URL, future=True)
    org, cli, doc, ver = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    conn = eng.connect()
    trans = conn.begin()
    try:
        _assert_non_superuser(conn)
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        _seed(conn, org, cli, doc, ver)
        conn.execute(text("SELECT set_config('app.current_org_id', :o, true)"), {"o": str(org)})
        conn.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        with pytest.raises(Exception):  # noqa: B017 -- kvkk_app UPDATE yetkisi yok, hata sinifi surucuye gore degisir
            conn.execute(
                text("UPDATE client_document_versions SET content = 'x' WHERE id = :i"),
                {"i": str(ver)},
            )
    finally:
        trans.rollback()
        conn.close()
        eng.dispose()
