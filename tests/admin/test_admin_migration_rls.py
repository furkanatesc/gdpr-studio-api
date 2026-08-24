import os
import uuid

import pytest
from sqlalchemy import create_engine, text

PG = os.getenv("ADMIN_RLS_TEST_DATABASE_URL")  # owner URL (tests swap to kvkk_admin_ro); ayrı var —
# tenant test_rls.py RLS_TEST_DATABASE_URL=kvkk_app ister, admin lane owner ister (çakışmaz)
pytestmark = pytest.mark.skipif(not PG, reason="requires Postgres owner URL (ADMIN_RLS_TEST_DATABASE_URL)")


def _role_url(pg, role):
    scheme, rest = pg.split("://", 1)
    hostpart = rest.split("@", 1)[1]
    return f"{scheme}://{role}:{role}@{hostpart}"


def _ro_url(pg):
    return _role_url(pg, "kvkk_admin_ro")


def _seq_name(conn, table):
    return conn.execute(text("SELECT pg_get_serial_sequence(:t, 'id')"), {"t": table}).scalar()


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


# --- G1: tenant app role (kvkk_app) must have ZERO access to platform back-office tables ---


@pytest.mark.parametrize("table", ["platform_audit_logs", "impersonation_sessions", "platform_admins", "platform_metrics_daily"])
def test_kvkk_app_cannot_select_platform_tables(table):
    eng = create_engine(_role_url(PG, "kvkk_app"))
    with eng.begin() as c, pytest.raises(Exception):  # noqa: B017 -- permission denied
        c.execute(text(f"SELECT count(*) FROM {table}"))  # cross-tenant metadata read path


def test_kvkk_app_cannot_delete_platform_audit():
    # 0003 default-privileges would otherwise give kvkk_app DELETE → append-only hole at role level
    eng = create_engine(_role_url(PG, "kvkk_app"))
    with eng.begin() as c, pytest.raises(Exception):  # noqa: B017 -- permission denied
        c.execute(text("DELETE FROM platform_audit_logs"))


# --- G3: sequence USAGE is least-privilege (only the owner role of each serial id) ---


def test_admin_ro_can_advance_audit_sequence():
    # sanity: G3 must NOT over-revoke — admin_ro still needs its audit id-seq to INSERT
    with create_engine(PG).connect() as c:
        seq = _seq_name(c, "platform_audit_logs")
    eng = create_engine(_ro_url(PG))
    with eng.begin() as c:
        c.execute(text(f"SELECT nextval('{seq}')"))  # no error = USAGE granted


def test_metrics_job_cannot_advance_audit_sequence():
    with create_engine(PG).connect() as c:
        seq = _seq_name(c, "platform_audit_logs")
    eng = create_engine(_role_url(PG, "kvkk_metrics_job"))
    with eng.begin() as c, pytest.raises(Exception):  # noqa: B017 -- not its sequence
        c.execute(text(f"SELECT nextval('{seq}')"))


def test_admin_ro_cannot_advance_metrics_sequence():
    with create_engine(PG).connect() as c:
        seq = _seq_name(c, "platform_metrics_daily")
    eng = create_engine(_ro_url(PG))
    with eng.begin() as c, pytest.raises(Exception):  # noqa: B017 -- not its sequence
        c.execute(text(f"SELECT nextval('{seq}')"))
