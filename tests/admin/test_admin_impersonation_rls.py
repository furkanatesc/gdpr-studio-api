"""impersonation_sessions kolon-bazlı GRANT — kvkk_admin_ro yalnız (ended_at, end_kind,
approved_by) UPDATE edebilir (bkz. 0020 grant amend, Task 8 PART A). sqlite'ta GÖRÜNMEZ
(kolon-bazlı GRANT postgres-only); bu dosya gerçek Postgres'e karşı koşar.
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text

PG = os.getenv("RLS_TEST_DATABASE_URL")  # owner URL — same gate style as tests/test_rls.py
pytestmark = pytest.mark.skipif(not PG, reason="requires Postgres owner URL")


def _ro_url(pg):
    # swap userinfo to kvkk_admin_ro:kvkk_admin_ro
    scheme, rest = pg.split("://", 1)
    hostpart = rest.split("@", 1)[1]
    return f"{scheme}://kvkk_admin_ro:kvkk_admin_ro@{hostpart}"


@pytest.fixture()
def seeded_session():
    """Owner URL ile bir platform_admin + impersonation_session ekler; testten sonra temizler."""
    eng = create_engine(PG, future=True)
    admin_id = uuid.uuid4()
    session_id = uuid.uuid4()
    org_id = uuid.uuid4()
    with eng.begin() as c:
        c.execute(
            text(
                "INSERT INTO platform_admins (id, supabase_user_id, email, is_active) "
                "VALUES (:id, :sub, :email, true)"
            ),
            {"id": admin_id, "sub": f"rls-sub-{admin_id}", "email": "rls@example.com"},
        )
        c.execute(
            text(
                "INSERT INTO impersonation_sessions "
                "(id, platform_admin_id, target_org_id, reason, scope, bound_sub, expires_at) "
                "VALUES (:id, :admin_id, :org_id, 'rls test', 'documents', 'sub', :expires_at)"
            ),
            {
                "id": session_id,
                "admin_id": admin_id,
                "org_id": org_id,
                "expires_at": datetime.now(UTC) + timedelta(minutes=30),
            },
        )

    yield session_id, admin_id

    with eng.begin() as c:
        c.execute(text("DELETE FROM impersonation_sessions WHERE id = :id"), {"id": session_id})
        c.execute(text("DELETE FROM platform_admins WHERE id = :id"), {"id": admin_id})
    eng.dispose()


def test_admin_ro_can_update_approved_by(seeded_session):
    session_id, admin_id = seeded_session
    eng = create_engine(_ro_url(PG))
    with eng.begin() as c:
        c.execute(
            text("UPDATE impersonation_sessions SET approved_by = :admin_id WHERE id = :id"),
            {"admin_id": admin_id, "id": session_id},
        )


def test_admin_ro_cannot_update_reason(seeded_session):
    session_id, _ = seeded_session
    eng = create_engine(_ro_url(PG))
    with eng.begin() as c, pytest.raises(Exception):  # noqa: B017 -- column-level GRANT excludes reason
        c.execute(
            text("UPDATE impersonation_sessions SET reason = 'x' WHERE id = :id"),
            {"id": session_id},
        )
