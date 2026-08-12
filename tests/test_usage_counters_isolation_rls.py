"""usage_counters için iki-org RLS izolasyon testi (B6). test_compliance_rls.py deseni."""
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
    assert not is_super, "RLS testleri non-superuser rolle (kvkk_app) koşmalı."


def _count_usage_in(conn, org_ids) -> int:
    return conn.execute(
        text("SELECT count(*) FROM usage_counters WHERE org_id = ANY(:oids)"),
        {"oids": [str(o) for o in org_ids]},
    ).scalar()


def test_usage_counters_rls_isolates_orgs_and_bypass_sees_all():
    eng = create_engine(DB_URL, future=True)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    conn = eng.connect()
    trans = conn.begin()
    try:
        _assert_non_superuser(conn)
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        for oid, name in [(org_a, "RLS Usage A"), (org_b, "RLS Usage B")]:
            conn.execute(
                text("INSERT INTO organizations (id, name) VALUES (:id, :name)"),
                {"id": oid, "name": name},
            )
        for oid in (org_a, org_b):
            conn.execute(
                text(
                    "INSERT INTO usage_counters (id, org_id, period, doc_count) "
                    "VALUES (:id, :oid, '2026-08', 0)"
                ),
                {"id": uuid.uuid4(), "oid": oid},
            )
        conn.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        conn.execute(text("SELECT set_config('app.current_org_id', :oid, true)"), {"oid": str(org_a)})
        assert _count_usage_in(conn, [org_a, org_b]) == 1  # B gizli
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        assert _count_usage_in(conn, [org_a, org_b]) == 2
    finally:
        trans.rollback()
        conn.close()
        eng.dispose()


def test_usage_counters_fail_closed_without_guc():
    eng = create_engine(DB_URL, future=True)
    conn = eng.connect()
    trans = conn.begin()
    try:
        _assert_non_superuser(conn)
        assert conn.execute(text("SELECT count(*) FROM usage_counters")).scalar() == 0
    finally:
        trans.rollback()
        conn.close()
        eng.dispose()
