"""TenantAdminRepository — gerçek Postgres/RLS altında liste+detay (Task 7 fix1).

Task 7 review'un yakaladığı 2 Critical (list() begin_provisioning yok → boş sayfa;
detail() set_org_context sıralaması yanlış → hep 404) sqlite'ta görünmez (RLS orada
no-op). Bu dosya kvkk_admin_ro rolüyle GERÇEK Postgres'e karşı koşar: pre-fix kodda
her iki test de FAIL ederdi (list boş liste döner, detail None döner).
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from admin_api.repositories import TenantAdminRepository

PG = os.getenv("ADMIN_RLS_TEST_DATABASE_URL")  # owner URL (tests swap to kvkk_admin_ro); ayrı var —
# tenant test_rls.py RLS_TEST_DATABASE_URL=kvkk_app ister, admin lane owner ister (çakışmaz)
pytestmark = pytest.mark.skipif(not PG, reason="requires Postgres owner URL (ADMIN_RLS_TEST_DATABASE_URL)")


def _ro_url(pg):
    # swap userinfo to kvkk_admin_ro:kvkk_admin_ro
    scheme, rest = pg.split("://", 1)
    hostpart = rest.split("@", 1)[1]
    return f"{scheme}://kvkk_admin_ro:kvkk_admin_ro@{hostpart}"


@pytest.fixture()
def seeded_orgs():
    """Owner URL ile bypass altında iki org+subscription ekler; testten sonra temizler."""
    eng = create_engine(PG, future=True)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    with eng.begin() as c:
        c.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        for oid, name in [(org_a, "RLS Tenant A"), (org_b, "RLS Tenant B")]:
            c.execute(
                text("INSERT INTO organizations (id, name, status) VALUES (:id, :name, 'active')"),
                {"id": oid, "name": name},
            )
        for oid in (org_a, org_b):
            c.execute(
                text(
                    "INSERT INTO subscriptions (id, org_id, plan, status) "
                    "VALUES (:id, :oid, 'baslangic', 'active')"
                ),
                {"id": uuid.uuid4(), "oid": oid},
            )

    yield org_a, org_b

    with eng.begin() as c:
        c.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        c.execute(
            text("DELETE FROM subscriptions WHERE org_id = ANY(:oids)"),
            {"oids": [str(org_a), str(org_b)]},
        )
        c.execute(
            text("DELETE FROM organizations WHERE id = ANY(:oids)"),
            {"oids": [str(org_a), str(org_b)]},
        )
    eng.dispose()


@pytest.fixture()
def ro_session():
    eng = create_engine(_ro_url(PG), future=True)
    session = sessionmaker(bind=eng, future=True)()
    yield session
    session.close()
    eng.dispose()


def test_list_sees_all_orgs_under_bypass(seeded_orgs, ro_session):
    org_a, org_b = seeded_orgs
    page = TenantAdminRepository(ro_session).list(q="RLS Tenant", limit=50)
    ids = {item["id"] for item in page["items"]}
    assert org_a in ids
    assert org_b in ids


def test_detail_returns_existing_org(seeded_orgs, ro_session):
    org_a, _ = seeded_orgs
    detail = TenantAdminRepository(ro_session).detail(org_a)
    assert detail is not None
    assert detail["id"] == org_a
    assert detail["plan"] == "baslangic"
    assert detail["subscription_status"] == "active"


def test_detail_missing_org_is_none(ro_session):
    assert TenantAdminRepository(ro_session).detail(uuid.uuid4()) is None
