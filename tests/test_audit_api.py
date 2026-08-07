"""GET /api/audit — yönetici-only, org-kapsamlı, imleç sayfalama, actor join."""

from __future__ import annotations

import contextlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import app.config as config_module
from app.auth.identity import Identity, get_current_identity
from app.db import get_session
from app.main import app
from app.models import AuditLog, User
from app.redis_client import reset_redis

_ORG = uuid.UUID("00000000-0000-0000-0000-000000000002")  # _DEV_IDENTITY org
_USER = uuid.UUID("00000000-0000-0000-0000-000000000001")  # _DEV_IDENTITY user
_BASE_TS = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


def _as_identity(role="yonetici", org_id=_ORG, user_id=_USER):
    return lambda: Identity(user_id=user_id, org_id=org_id, role=role, email="x@y.io")


@contextlib.contextmanager
def _as_role(role):
    app.dependency_overrides[get_current_identity] = _as_identity(role=role)
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_current_identity, None)


@contextlib.contextmanager
def _auth_enforced_client(db_session):
    """Auth zorunlu (dev-bypass kapalı, supabase URL set, dev env) → Bearer yoksa 401."""
    prev = config_module._settings
    config_module._settings = config_module.Settings(
        _env_file=None,
        managed_anthropic_api_key="",
        allowed_origins="http://localhost:3000",
        redis_url="",
        supabase_project_url="https://x.supabase.co",
        auth_dev_bypass=False,
        environment="development",
    )
    reset_redis()

    def _ov():
        yield db_session

    app.dependency_overrides[get_session] = _ov
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        config_module._settings = prev
        reset_redis()


@pytest.fixture()
def seeded_audit_rows(db_session):
    db_session.add(User(id=_USER, supabase_user_id="dev-user", email="dev@kvkkyonetim.local"))
    rows = []
    actions = ["membership.role_changed", "compliance.status_changed", "membership.role_changed"]
    for i, action in enumerate(actions):
        row = AuditLog(
            org_id=_ORG, actor_user_id=_USER, action=action,
            target_type="membership", target_id=str(uuid.uuid4()),
            created_at=_BASE_TS + timedelta(minutes=i),
        )
        db_session.add(row)
        rows.append(row)
    db_session.commit()
    return rows


@pytest.fixture()
def audit_row_orphan_actor(db_session):
    row = AuditLog(
        org_id=_ORG, actor_user_id=None, action="invite.revoked",
        target_type="invite", target_id="x", created_at=_BASE_TS,
    )
    db_session.add(row)
    db_session.commit()
    return row


def test_audit_requires_auth(db_session):
    with _auth_enforced_client(db_session) as c:
        assert c.get("/api/audit").status_code == 401


def test_audit_forbidden_for_avukat(client, db_session):
    with _as_role("avukat"):
        assert client.get("/api/audit").status_code == 403


def test_audit_lists_events_desc_and_paginates(client, seeded_audit_rows):
    r = client.get("/api/audit?limit=2")
    assert r.status_code == 200
    j = r.json()
    assert len(j["items"]) == 2
    assert j["nextCursor"]
    # created_at DESC → en yeni satır (i=2) ilk sırada
    assert j["items"][0]["createdAt"] > j["items"][1]["createdAt"]
    assert all(it["actorEmail"] == "dev@kvkkyonetim.local" for it in j["items"])


def test_audit_pagination_reaches_last_page(client, seeded_audit_rows):
    r1 = client.get("/api/audit?limit=2")
    cursor = r1.json()["nextCursor"]
    r2 = client.get("/api/audit", params={"limit": 2, "before": cursor})
    assert r2.status_code == 200
    j2 = r2.json()
    assert len(j2["items"]) == 1
    assert j2["nextCursor"] is None


def test_audit_actor_deleted_shows_dash(client, audit_row_orphan_actor):
    r = client.get("/api/audit")
    assert r.status_code == 200
    assert any(it["actorEmail"] == "—" for it in r.json()["items"])


def test_audit_action_filter(client, seeded_audit_rows):
    r = client.get("/api/audit?action=membership.role_changed")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items
    assert all(it["action"] == "membership.role_changed" for it in items)
