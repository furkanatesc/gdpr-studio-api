"""compliance_status + generated_documents için iki-org RLS izolasyon testi.

test_rls.py deseninin birebir kopyası (FORCE ROW LEVEL SECURITY, kvkk_app non-superuser).
Postgres-gated: RLS_TEST_DATABASE_URL yoksa skip. Tek transaction → rollback (kirlilik yok).
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


def _count_status_in(conn, org_ids) -> int:
    return conn.execute(
        text("SELECT count(*) FROM compliance_status WHERE org_id = ANY(:oids)"),
        {"oids": [str(o) for o in org_ids]},
    ).scalar()


def _count_docs_in(conn, org_ids) -> int:
    return conn.execute(
        text("SELECT count(*) FROM generated_documents WHERE org_id = ANY(:oids)"),
        {"oids": [str(o) for o in org_ids]},
    ).scalar()


def test_compliance_status_rls_isolates_orgs_and_bypass_sees_all():
    eng = create_engine(DB_URL, future=True)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()

    conn = eng.connect()
    trans = conn.begin()
    try:
        _assert_non_superuser(conn)
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        for oid, name in [(org_a, "RLS Comp A"), (org_b, "RLS Comp B")]:
            conn.execute(
                text("INSERT INTO organizations (id, name) VALUES (:id, :name)"),
                {"id": oid, "name": name},
            )
        for oid in (org_a, org_b):
            conn.execute(
                text(
                    "INSERT INTO compliance_status (id, org_id, requirement_key, status, source) "
                    "VALUES (:id, :oid, 'k', 'yapildi', 'user')"
                ),
                {"id": uuid.uuid4(), "oid": oid},
            )
            conn.execute(
                text(
                    "INSERT INTO generated_documents (id, org_id, doc_type) "
                    "VALUES (:id, :oid, 'aydinlatma')"
                ),
                {"id": uuid.uuid4(), "oid": oid},
            )

        # İZOLASYON: bypass kapalı, org A bağlamı → yalnız A görünür.
        conn.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        conn.execute(
            text("SELECT set_config('app.current_org_id', :oid, true)"),
            {"oid": str(org_a)},
        )
        assert _count_status_in(conn, [org_a, org_b]) == 1  # B gizli
        assert _count_docs_in(conn, [org_a, org_b]) == 1  # B gizli

        # BYPASS: provisioning bağlamı → her ikisi de görünür.
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        assert _count_status_in(conn, [org_a, org_b]) == 2
        assert _count_docs_in(conn, [org_a, org_b]) == 2
    finally:
        trans.rollback()
        conn.close()
        eng.dispose()


def test_compliance_fail_closed_without_guc():
    """GUC set edilmemiş (NULL) → policy false → sıfır satır (fail-closed)."""
    eng = create_engine(DB_URL, future=True)
    conn = eng.connect()
    trans = conn.begin()
    try:
        _assert_non_superuser(conn)
        assert conn.execute(text("SELECT count(*) FROM compliance_status")).scalar() == 0
        assert conn.execute(text("SELECT count(*) FROM generated_documents")).scalar() == 0
    finally:
        trans.rollback()
        conn.close()
        eng.dispose()
