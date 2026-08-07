"""audit_logs append-only (REVOKE UPDATE/DELETE) + iki-org RLS izolasyon testi.

test_client_document_versions_rls.py / test_compliance_rls.py deseninin birebir kopyası
(FORCE ROW LEVEL SECURITY, kvkk_app non-superuser). Postgres-gated: RLS_TEST_DATABASE_URL
yoksa skip. Tek transaction → rollback (kirlilik yok).
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text

DB_URL = os.getenv("RLS_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not DB_URL, reason="RLS yalnız Postgres'te; RLS_TEST_DATABASE_URL gerekli")


def _assert_non_superuser(conn) -> None:
    is_super = conn.execute(
        text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
    ).scalar()
    assert not is_super, (
        "RLS testleri non-superuser rolle (kvkk_app) koşmalı; superuser RLS'i bypass "
        "eder → test anlamsızca geçer. RLS_TEST_DATABASE_URL'i kvkk_app'e yönlendirin."
    )


def _seed_org(conn, org) -> None:
    conn.execute(text("INSERT INTO organizations (id, name) VALUES (:id, 'O')"), {"id": str(org)})


def _seed_audit_row(conn, org, row_id) -> None:
    conn.execute(
        text(
            "INSERT INTO audit_logs (id, org_id, action) VALUES (:id, :o, 'test.action')"
        ),
        {"id": str(row_id), "o": str(org)},
    )


def test_audit_log_update_delete_rejected():
    """UPDATE/DELETE, RLS değil REVOKE ile reddedilir (append-only)."""
    eng = create_engine(DB_URL, future=True)
    org, row_id = uuid.uuid4(), uuid.uuid4()
    conn = eng.connect()
    trans = conn.begin()
    try:
        _assert_non_superuser(conn)
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        _seed_org(conn, org)
        _seed_audit_row(conn, org, row_id)
        conn.execute(text("SELECT set_config('app.current_org_id', :o, true)"), {"o": str(org)})
        conn.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))

        savepoint = conn.begin_nested()
        with pytest.raises(Exception):  # noqa: B017 -- kvkk_app UPDATE yetkisi yok (REVOKE)
            conn.execute(
                text("UPDATE audit_logs SET action = 'x' WHERE id = :i"), {"i": str(row_id)}
            )
        savepoint.rollback()

        savepoint = conn.begin_nested()
        with pytest.raises(Exception):  # noqa: B017 -- kvkk_app DELETE yetkisi yok (REVOKE)
            conn.execute(text("DELETE FROM audit_logs WHERE id = :i"), {"i": str(row_id)})
        savepoint.rollback()
    finally:
        trans.rollback()
        conn.close()
        eng.dispose()


def test_audit_log_cross_org_isolation():
    """Org A bağlamıyla INSERT edilen satır, org B bağlamında görünmez (RLS)."""
    eng = create_engine(DB_URL, future=True)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    row_a = uuid.uuid4()
    conn = eng.connect()
    trans = conn.begin()
    try:
        _assert_non_superuser(conn)
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        _seed_org(conn, org_a)
        _seed_org(conn, org_b)
        _seed_audit_row(conn, org_a, row_a)

        conn.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        conn.execute(text("SELECT set_config('app.current_org_id', :o, true)"), {"o": str(org_b)})
        cnt_b = conn.execute(
            text("SELECT count(*) FROM audit_logs WHERE org_id = ANY(:oids)"),
            {"oids": [str(org_a), str(org_b)]},
        ).scalar()
        assert cnt_b == 0  # A gizli

        conn.execute(text("SELECT set_config('app.current_org_id', :o, true)"), {"o": str(org_a)})
        cnt_a = conn.execute(
            text("SELECT count(*) FROM audit_logs WHERE org_id = ANY(:oids)"),
            {"oids": [str(org_a), str(org_b)]},
        ).scalar()
        assert cnt_a == 1
    finally:
        trans.rollback()
        conn.close()
        eng.dispose()
