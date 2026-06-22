import os

import pytest
from sqlalchemy import create_engine, text

DB_URL = os.getenv("RLS_TEST_DATABASE_URL")  # ör. postgresql+psycopg://kvkk:kvkk@localhost:5432/kvkk

pytestmark = pytest.mark.skipif(not DB_URL, reason="RLS yalnız Postgres'te; RLS_TEST_DATABASE_URL gerekli")


def test_rls_blocks_cross_tenant():
    eng = create_engine(DB_URL, future=True)
    with eng.begin() as conn:
        conn.execute(text("SELECT set_config('app.current_org_id', :oid, true)"),
                     {"oid": "00000000-0000-0000-0000-000000000000"})
        rows = conn.execute(text("SELECT count(*) FROM memberships")).scalar()
        assert rows == 0  # bu org'a ait üyelik yok → RLS diğerlerini gizler
