"""GET /admin/audit — id-desc keyset pagination, integrity fields excluded from response."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from admin_api.audit import write_audit
from admin_api.auth import PlatformAdminIdentity, require_platform_admin
from admin_api.db import admin_session
from admin_api.main import app
from app.db import Base

_IDENTITY = PlatformAdminIdentity(
    "11111111-1111-1111-1111-111111111111", "sub", "a@b.co", "sub"
)
_ACTOR = SimpleNamespace(admin_id=_IDENTITY.admin_id, email=_IDENTITY.email)


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

    for i in range(3):
        write_audit(session, actor=_ACTOR, action=f"action.{i}", reason=f"r{i}")

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


def test_list_returns_entries_camel_case_no_hash_fields(client):
    resp = client.get("/admin/audit")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 3
    first = body["items"][0]
    assert "actorEmailSnapshot" in first
    assert "resultRowCount" in first
    assert "createdAt" in first
    assert "targetOrgId" in first
    assert "rowHash" not in first
    assert "prevHash" not in first


def test_list_ordered_id_desc(client):
    resp = client.get("/admin/audit")
    ids = [item["id"] for item in resp.json()["items"]]
    assert ids == sorted(ids, reverse=True)


def test_cursor_paging_no_overlap(client):
    page1 = client.get("/admin/audit", params={"limit": 2})
    assert page1.status_code == 200
    body1 = page1.json()
    assert len(body1["items"]) == 2
    assert body1["nextCursor"] is not None

    page2 = client.get("/admin/audit", params={"limit": 2, "cursor": body1["nextCursor"]})
    assert page2.status_code == 200
    body2 = page2.json()
    assert len(body2["items"]) == 1
    assert body2["nextCursor"] is None

    ids1 = {item["id"] for item in body1["items"]}
    ids2 = {item["id"] for item in body2["items"]}
    assert ids1.isdisjoint(ids2)


def test_limit_bounds_rejected(client):
    assert client.get("/admin/audit", params={"limit": 0}).status_code == 422
    assert client.get("/admin/audit", params={"limit": 201}).status_code == 422


def test_malformed_cursor_rejected(client):
    resp = client.get("/admin/audit", params={"cursor": "notanint"})
    assert resp.status_code == 422
