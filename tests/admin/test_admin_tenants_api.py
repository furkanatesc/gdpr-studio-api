import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from admin_api.auth import PlatformAdminIdentity, require_platform_admin
from admin_api.db import admin_session
from admin_api.main import app
from app.db import Base
from app.models import Membership, Organization, Subscription, User

_IDENTITY = PlatformAdminIdentity(
    "11111111-1111-1111-1111-111111111111", "sub", "a@b.co", "sub"
)

_BASE_TS = datetime(2024, 1, 1, tzinfo=UTC)

ORG_ACTIVE_1 = uuid.UUID("00000000-0000-0000-0000-000000000001")
ORG_ACTIVE_2 = uuid.UUID("00000000-0000-0000-0000-000000000002")
ORG_SUSPENDED = uuid.UUID("00000000-0000-0000-0000-000000000003")


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()

    session.add_all(
        [
            Organization(
                id=ORG_ACTIVE_1,
                name="Acme Hukuk",
                sector="hukuk",
                status="active",
                created_at=_BASE_TS,
            ),
            Organization(
                id=ORG_ACTIVE_2,
                name="Beta Danismanlik",
                sector="danismanlik",
                status="active",
                created_at=_BASE_TS + timedelta(days=1),
            ),
            Organization(
                id=ORG_SUSPENDED,
                name="Gamma Suspended",
                sector="hukuk",
                status="suspended",
                created_at=_BASE_TS + timedelta(days=2),
            ),
        ]
    )
    session.add_all(
        [
            Subscription(org_id=ORG_ACTIVE_1, plan="premium", status="active"),
            Subscription(org_id=ORG_ACTIVE_2, plan="baslangic", status="active"),
            Subscription(org_id=ORG_SUSPENDED, plan="standart", status="canceled"),
        ]
    )

    user1 = User(supabase_user_id="sb-1", email="u1@acme.test")
    user2 = User(supabase_user_id="sb-2", email="u2@acme.test")
    session.add_all([user1, user2])
    session.flush()
    session.add_all(
        [
            Membership(user_id=user1.id, org_id=ORG_ACTIVE_1, role="yonetici"),
            Membership(user_id=user2.id, org_id=ORG_ACTIVE_1, role="avukat"),
        ]
    )
    session.commit()

    yield session

    session.close()


@pytest.fixture()
def client(session_factory):
    session = session_factory

    def _override_session():
        yield session

    app.dependency_overrides[require_platform_admin] = lambda: _IDENTITY
    app.dependency_overrides[admin_session] = _override_session

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


def test_list_returns_orgs(client):
    resp = client.get("/admin/tenants")
    assert resp.status_code == 200
    body = resp.json()
    assert "items" in body
    assert "nextCursor" in body
    names = {item["name"] for item in body["items"]}
    assert names == {"Acme Hukuk", "Beta Danismanlik", "Gamma Suspended"}


def test_list_filters_by_status(client):
    resp = client.get("/admin/tenants", params={"status": "active"})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert all(item["status"] == "active" for item in body["items"])


def test_detail_returns_single_org(client):
    resp = client.get(f"/admin/tenants/{ORG_ACTIVE_1}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == str(ORG_ACTIVE_1)
    assert body["plan"] == "premium"
    assert body["subscriptionStatus"] == "active"
    assert body["memberCount"] == 2

    missing = client.get(f"/admin/tenants/{uuid.uuid4()}")
    assert missing.status_code == 404


def test_list_cursor_second_page(client):
    page1 = client.get("/admin/tenants", params={"limit": 2})
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["items"]) == 2
    assert body1["nextCursor"] is not None

    page2 = client.get("/admin/tenants", params={"limit": 2, "cursor": body1["nextCursor"]})
    assert page2.status_code == 200
    body2 = page2.json()
    assert body2["nextCursor"] is None

    names1 = {item["name"] for item in body1["items"]}
    names2 = {item["name"] for item in body2["items"]}
    assert names1.isdisjoint(names2)
    assert names1 | names2 == {"Acme Hukuk", "Beta Danismanlik", "Gamma Suspended"}


def test_list_malformed_cursor_returns_4xx(client):
    resp = client.get("/admin/tenants", params={"cursor": "not-a-valid-cursor"})
    assert resp.status_code in (400, 422)


def test_list_filters_by_q(client):
    resp = client.get("/admin/tenants", params={"q": "acme"})
    assert resp.status_code == 200
    body = resp.json()
    names = {item["name"] for item in body["items"]}
    assert names == {"Acme Hukuk"}
