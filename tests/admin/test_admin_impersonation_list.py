"""GET /admin/impersonation — platform-geneli oturum listesi, (started_at, id) DESC keyset.

Liste back-office oversight/dual-control iş akışı içindir: bir onaylayıcının BAŞKA admin'in
bekleyen oturumunu bulabilmesi için platform-geneli döner (audit log gibi). Kiracı verisi YOK
— yalnız oturum metadata'sı → legal-gate uygulanmaz (start/read gate'li, liste değil).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from admin_api.auth import PlatformAdminIdentity, require_platform_admin
from admin_api.db import admin_session
from admin_api.main import app
from app.db import Base
from app.models import ImpersonationSession, PlatformAdmin

ADMIN_A_ID = "11111111-1111-1111-1111-111111111111"
ADMIN_B_ID = "22222222-2222-2222-2222-222222222222"

_IDENTITY = PlatformAdminIdentity(ADMIN_A_ID, "sub-a", "a@example.com", "sub-a")

TARGET_ORG = uuid.UUID("33333333-3333-3333-3333-333333333333")

_BASE = datetime(2026, 8, 26, 12, 0, 0, tzinfo=UTC)


def _seed(session, *, admin_id: str, started_at: datetime, scope: str = "documents") -> uuid.UUID:
    row = ImpersonationSession(
        platform_admin_id=uuid.UUID(admin_id),
        target_org_id=TARGET_ORG,
        reason="inceleme",
        scope=scope,
        requires_dual_control=(scope == "ozel_nitelikli"),
        bound_sub="sub",
        started_at=started_at,
        expires_at=started_at + timedelta(minutes=30),
    )
    session.add(row)
    session.commit()
    return row.id


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
            PlatformAdmin(
                id=uuid.UUID(ADMIN_A_ID),
                supabase_user_id="sub-a",
                email="a@example.com",
                is_active=True,
            ),
            PlatformAdmin(
                id=uuid.UUID(ADMIN_B_ID),
                supabase_user_id="sub-b",
                email="b@example.com",
                is_active=True,
            ),
        ]
    )
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def client(session_factory):
    def _override_session():
        yield session_factory

    app.dependency_overrides[require_platform_admin] = lambda: _IDENTITY
    app.dependency_overrides[admin_session] = _override_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_list_empty_returns_no_items(client):
    resp = client.get("/admin/impersonation")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["nextCursor"] is None


def test_list_returns_sessions_newest_first(client, session_factory):
    older = _seed(session_factory, admin_id=ADMIN_A_ID, started_at=_BASE - timedelta(minutes=5))
    newer = _seed(session_factory, admin_id=ADMIN_A_ID, started_at=_BASE)

    resp = client.get("/admin/impersonation")
    assert resp.status_code == 200
    ids = [item["id"] for item in resp.json()["items"]]
    assert ids == [str(newer), str(older)]


def test_list_returns_all_admins_sessions(client, session_factory):
    _seed(session_factory, admin_id=ADMIN_A_ID, started_at=_BASE - timedelta(minutes=1))
    b_id = _seed(session_factory, admin_id=ADMIN_B_ID, started_at=_BASE)

    resp = client.get("/admin/impersonation")
    ids = {item["id"] for item in resp.json()["items"]}
    # Onaylayıcı (A) başka admin'in (B) oturumunu görebilmeli — dual-control gereği.
    assert str(b_id) in ids


def test_list_response_shape_camel_case(client, session_factory):
    _seed(session_factory, admin_id=ADMIN_A_ID, started_at=_BASE, scope="ozel_nitelikli")

    first = client.get("/admin/impersonation").json()["items"][0]
    assert "platformAdminId" in first
    assert "targetOrgId" in first
    assert "requiresDualControl" in first
    assert "approvedBy" in first
    assert "startedAt" in first
    assert "expiresAt" in first
    assert "endKind" in first


def test_list_keyset_pagination_no_overlap(client, session_factory):
    for i in range(3):
        _seed(session_factory, admin_id=ADMIN_A_ID, started_at=_BASE - timedelta(minutes=i))

    page1 = client.get("/admin/impersonation", params={"limit": 2})
    body1 = page1.json()
    assert len(body1["items"]) == 2
    assert body1["nextCursor"] is not None

    page2 = client.get(
        "/admin/impersonation", params={"limit": 2, "cursor": body1["nextCursor"]}
    )
    body2 = page2.json()
    assert len(body2["items"]) == 1
    assert body2["nextCursor"] is None

    ids1 = {item["id"] for item in body1["items"]}
    ids2 = {item["id"] for item in body2["items"]}
    assert ids1.isdisjoint(ids2)


def test_list_limit_bounds_rejected(client):
    assert client.get("/admin/impersonation", params={"limit": 0}).status_code == 422
    assert client.get("/admin/impersonation", params={"limit": 201}).status_code == 422


def test_list_malformed_cursor_rejected(client):
    resp = client.get("/admin/impersonation", params={"cursor": "notacursor"})
    assert resp.status_code == 422


def test_list_requires_platform_admin(session_factory):
    def _reject():
        raise HTTPException(status_code=401, detail="missing_token")

    def _override_session():
        yield session_factory

    app.dependency_overrides[require_platform_admin] = _reject
    app.dependency_overrides[admin_session] = _override_session
    try:
        with TestClient(app) as c:
            resp = c.get("/admin/impersonation")
        assert resp.status_code == 401
    finally:
        app.dependency_overrides.clear()
