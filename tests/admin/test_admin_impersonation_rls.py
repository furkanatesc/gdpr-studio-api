"""impersonation_sessions kolon-bazlı GRANT — kvkk_admin_ro yalnız (ended_at, end_kind,
approved_by) UPDATE edebilir (bkz. 0020 grant amend, Task 8 PART A). sqlite'ta GÖRÜNMEZ
(kolon-bazlı GRANT postgres-only); bu dosya gerçek Postgres'e karşı koşar.

Ayrıca Task 9 izolasyon testleri: `assert_bypass_off` gerçek bypass GUC'una karşı +
SEC-C2 (aggregate-sonra-impersonate cross-tenant sızıntı yok) — bu ikisi de kvkk_admin_ro
rolüyle gerçek Postgres gerektirir, sqlite'ta anlamsız (RLS/bypass no-op).
"""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from admin_api.db import assert_bypass_off
from admin_api.modules.impersonation import SCOPE_READERS
from app.auth.tenant_session import begin_provisioning, end_provisioning, set_org_context

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


def test_read_requires_bypass_off():
    """A dirty bypass window (left ON from an earlier step in the same session) must abort
    a scoped impersonation read — `assert_bypass_off` is the last line of defense."""
    eng = create_engine(_ro_url(PG), future=True)
    session = sessionmaker(bind=eng, future=True)()
    try:
        session.execute(text("SELECT set_config('app.bypass_rls','on',true)"))
        with pytest.raises(RuntimeError):
            assert_bypass_off(session)
    finally:
        session.close()
        eng.dispose()


SCOPE_IDENTITY_FIELD = {
    "clients": "id",
    "compliance": "requirementKey",
    "documents_meta": "id",
    "ozel_nitelikli": "id",
}


@pytest.fixture()
def seeded_orgs_with_clients():
    """Owner URL ile bypass altında iki org + birer client + her SCOPE_READERS okuyucusunun
    arkasındaki tabloda birer satır ekler (SEC-C2, 4 kapsam için); testten sonra temizler."""
    eng = create_engine(PG, future=True)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    client_a, client_b = uuid.uuid4(), uuid.uuid4()
    doc_a, doc_b = uuid.uuid4(), uuid.uuid4()
    proc_a, proc_b = uuid.uuid4(), uuid.uuid4()
    seed_ids = {
        "clients": (client_a, client_b),
        "compliance": ("sec-c2-req-a", "sec-c2-req-b"),
        "documents_meta": (doc_a, doc_b),
        "ozel_nitelikli": (proc_a, proc_b),
    }
    with eng.begin() as c:
        c.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        for oid, name in [(org_a, "SEC-C2 Org A"), (org_b, "SEC-C2 Org B")]:
            c.execute(
                text("INSERT INTO organizations (id, name, status) VALUES (:id, :name, 'active')"),
                {"id": oid, "name": name},
            )
        for cid, oid, name in [(client_a, org_a, "SEC-C2 Client A"), (client_b, org_b, "SEC-C2 Client B")]:
            c.execute(
                text("INSERT INTO clients (id, org_id, name) VALUES (:id, :oid, :name)"),
                {"id": cid, "oid": oid, "name": name},
            )
        for oid, key in [(org_a, "sec-c2-req-a"), (org_b, "sec-c2-req-b")]:
            c.execute(
                text(
                    "INSERT INTO compliance_status (id, org_id, requirement_key, status) "
                    "VALUES (:id, :oid, :key, 'yapildi')"
                ),
                {"id": uuid.uuid4(), "oid": oid, "key": key},
            )
        for did, oid in [(doc_a, org_a), (doc_b, org_b)]:
            c.execute(
                text(
                    "INSERT INTO generated_documents (id, org_id, doc_type) "
                    "VALUES (:id, :oid, 'aydinlatma')"
                ),
                {"id": did, "oid": oid},
            )
        for pid, oid, cid, ad in [
            (proc_a, org_a, client_a, "SEC-C2 Proc A"),
            (proc_b, org_b, client_b, "SEC-C2 Proc B"),
        ]:
            c.execute(
                text(
                    "INSERT INTO client_processors (id, org_id, client_id, ad, unvan) "
                    "VALUES (:id, :oid, :cid, :ad, 'A.Ş.')"
                ),
                {"id": pid, "oid": oid, "cid": cid, "ad": ad},
            )

    yield org_a, org_b, seed_ids

    with eng.begin() as c:
        c.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        c.execute(
            text("DELETE FROM client_processors WHERE org_id = ANY(:oids)"),
            {"oids": [str(org_a), str(org_b)]},
        )
        c.execute(
            text("DELETE FROM generated_documents WHERE org_id = ANY(:oids)"),
            {"oids": [str(org_a), str(org_b)]},
        )
        c.execute(
            text("DELETE FROM compliance_status WHERE org_id = ANY(:oids)"),
            {"oids": [str(org_a), str(org_b)]},
        )
        c.execute(
            text("DELETE FROM clients WHERE org_id = ANY(:oids)"),
            {"oids": [str(org_a), str(org_b)]},
        )
        c.execute(
            text("DELETE FROM organizations WHERE id = ANY(:oids)"),
            {"oids": [str(org_a), str(org_b)]},
        )
    eng.dispose()


@pytest.mark.parametrize("scope", ["clients", "compliance", "documents_meta", "ozel_nitelikli"])
def test_aggregate_then_impersonate_does_not_leak_foreign_rows(scope, seeded_orgs_with_clients):
    """SEC-C2 — the core guarantee: an unrelated cross-tenant aggregate window (bypass on,
    then off) in one kvkk_admin_ro session must NOT leak into a scoped impersonation read run
    in a FRESH kvkk_admin_ro session/connection afterwards. Parametrized over all four shipped
    scopes — each backing table (clients/compliance_status/generated_documents/client_processors)
    carries an equivalent org_id-keyed FORCE RLS policy."""
    org_a, org_b, seed_ids = seeded_orgs_with_clients

    eng1 = create_engine(_ro_url(PG), future=True)
    s1 = sessionmaker(bind=eng1, future=True)()
    try:
        begin_provisioning(s1)
        count = s1.execute(text("SELECT count(*) FROM organizations")).scalar_one()
        assert count >= 2  # aggregate window genuinely sees across tenants
        end_provisioning(s1)
        s1.commit()
    finally:
        s1.close()
        eng1.dispose()

    eng2 = create_engine(_ro_url(PG), future=True)
    s2 = sessionmaker(bind=eng2, future=True)()
    try:
        set_org_context(s2, org_a)
        rows = SCOPE_READERS[scope](s2, org_a)
        field = SCOPE_IDENTITY_FIELD[scope]
        values = {r[field] for r in rows}
        value_a, value_b = seed_ids[scope]
        assert value_a in values
        assert value_b not in values
    finally:
        s2.close()
        eng2.dispose()
