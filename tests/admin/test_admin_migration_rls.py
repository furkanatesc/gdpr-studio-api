import os
import uuid

import pytest
from sqlalchemy import create_engine, text

PG = os.getenv("RLS_TEST_DATABASE_URL")  # owner URL — same gate style as tests/test_rls.py
pytestmark = pytest.mark.skipif(not PG, reason="requires Postgres owner URL")


def _ro_url(pg):
    # swap userinfo to kvkk_admin_ro:kvkk_admin_ro
    scheme, rest = pg.split("://", 1)
    hostpart = rest.split("@", 1)[1]
    return f"{scheme}://kvkk_admin_ro:kvkk_admin_ro@{hostpart}"


def test_admin_ro_cannot_write_tenant_table_even_under_bypass():
    eng = create_engine(_ro_url(PG))
    with eng.begin() as c:
        c.execute(text("SELECT set_config('app.bypass_rls','on',true)"))
        with pytest.raises(Exception):  # noqa: B017 -- kvkk_admin_ro yetkisi yok (insufficient privilege)
            c.execute(text("INSERT INTO organizations (id,name,status) VALUES (:i,'x','active')"),
                      {"i": str(uuid.uuid4())})


def test_admin_ro_can_select_all_tenant_rows_under_bypass():
    eng = create_engine(_ro_url(PG))
    with eng.begin() as c:
        c.execute(text("SELECT set_config('app.bypass_rls','on',true)"))
        c.execute(text("SELECT count(*) FROM organizations"))  # no error = SELECT granted


def test_platform_audit_is_append_only_for_admin_ro():
    eng = create_engine(_ro_url(PG))
    with eng.begin() as c, pytest.raises(Exception):  # noqa: B017 -- append-only REVOKE
        c.execute(text("DELETE FROM platform_audit_logs"))
