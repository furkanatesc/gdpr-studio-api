"""Impersonation okuma vekili — bypass-off assert, kapsam eşleşmesi, fail-closed audit, hacim sınırı.

sqlite: `assert_bypass_off` postgres-only no-op olduğundan izolasyonun kendisi burada
GÖRÜNMEZ — yalnız kontrol-akışı (kapsam eşleşme/bilinmeyen kapsam, audit, hacim sınırı,
dual-control) test edilir. SEC-C2 izolasyon kanıtı PG-gated `test_admin_impersonation_rls.py`'de.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import admin_api.modules.impersonation as impersonation_module
from admin_api.auth import PlatformAdminIdentity, require_platform_admin
from admin_api.config import AdminSettings
from admin_api.db import admin_session
from admin_api.main import app
from app.db import Base
from app.models import (
    Client,
    ClientProcessor,
    ComplianceStatus,
    GeneratedDocument,
    ImpersonationSession,
    PlatformAdmin,
    PlatformAuditLog,
)

ADMIN_A_ID = "11111111-1111-1111-1111-111111111111"
ADMIN_B_ID = "22222222-2222-2222-2222-222222222222"

IDENTITY_A = PlatformAdminIdentity(ADMIN_A_ID, "sub-a", "a@example.com", "sub-a")
IDENTITY_B = PlatformAdminIdentity(ADMIN_B_ID, "sub-b", "b@example.com", "sub-b")

TARGET_ORG = uuid.UUID("33333333-3333-3333-3333-333333333333")


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


def _make_client(
    session,
    identity,
    monkeypatch,
    *,
    volume_cap: int = 5000,
    raise_server_exceptions: bool = True,
    legal_ready: bool = True,
) -> TestClient:
    def _override_session():
        yield session

    app.dependency_overrides[require_platform_admin] = lambda: identity
    app.dependency_overrides[admin_session] = _override_session
    monkeypatch.setattr(
        impersonation_module,
        "get_admin_settings",
        lambda: AdminSettings(h5_legal_ready=legal_ready, impersonation_volume_cap=volume_cap),
    )
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


@pytest.fixture()
def client(session_factory, monkeypatch):
    c = _make_client(session_factory, IDENTITY_A, monkeypatch)
    yield c
    app.dependency_overrides.clear()


def _seed_session(
    session_factory,
    *,
    scope: str = "clients",
    requires_dual_control: bool = False,
    approved_by: uuid.UUID | None = None,
    expires_at: datetime | None = None,
    ended_at: datetime | None = None,
    admin_id: str = ADMIN_A_ID,
    bound_sub: str = "sub-a",
) -> ImpersonationSession:
    row = ImpersonationSession(
        platform_admin_id=uuid.UUID(admin_id),
        target_org_id=TARGET_ORG,
        reason="inceleme",
        scope=scope,
        requires_dual_control=requires_dual_control,
        approved_by=approved_by,
        bound_sub=bound_sub,
        expires_at=expires_at or (datetime.now(UTC) + timedelta(minutes=30)),
        ended_at=ended_at,
    )
    session_factory.add(row)
    session_factory.commit()
    return row


def _seed_target_org_data(session_factory) -> None:
    client_a_id = uuid.uuid4()
    session_factory.add_all(
        [
            Client(id=client_a_id, org_id=TARGET_ORG, name="Müvekkil A", sector="finans"),
            Client(id=uuid.uuid4(), org_id=TARGET_ORG, name="Müvekkil B", sector="saglik"),
            ComplianceStatus(
                org_id=TARGET_ORG, requirement_key="req-1", status="yapildi", source="user"
            ),
            ComplianceStatus(
                org_id=TARGET_ORG, requirement_key="req-2", status="eksik", source="user"
            ),
            GeneratedDocument(org_id=TARGET_ORG, doc_type="aydinlatma"),
            GeneratedDocument(org_id=TARGET_ORG, doc_type="cerez"),
            ClientProcessor(
                org_id=TARGET_ORG,
                client_id=client_a_id,
                ad="İşleyen A",
                unvan="A A.Ş.",
            ),
            ClientProcessor(
                org_id=TARGET_ORG,
                client_id=client_a_id,
                ad="İşleyen B",
                unvan="B A.Ş.",
            ),
        ]
    )
    session_factory.commit()


def test_read_requires_active_session(client, session_factory):
    row = _seed_session(session_factory, expires_at=datetime.now(UTC) - timedelta(minutes=1))
    resp = client.get(f"/admin/impersonation/{row.id}/clients")
    assert resp.status_code == 403


def test_read_requires_legal_ready(session_factory, monkeypatch):
    row = _seed_session(session_factory, scope="clients")
    c = _make_client(session_factory, IDENTITY_A, monkeypatch, legal_ready=False)
    try:
        resp = c.get(f"/admin/impersonation/{row.id}/clients")
        assert resp.status_code == 403
        assert resp.json()["detail"] == "h5_legal_not_ready"
    finally:
        app.dependency_overrides.clear()


def test_read_scope_must_match_session(client, session_factory):
    row = _seed_session(session_factory, scope="clients")
    resp = client.get(f"/admin/impersonation/{row.id}/documents_meta")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "scope_mismatch"


def test_unknown_scope_404(client, session_factory):
    row = _seed_session(session_factory, scope="clients")
    resp = client.get(f"/admin/impersonation/{row.id}/nonsense")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "unknown_scope"


def test_read_writes_viewed_audit_with_row_count(client, session_factory):
    _seed_target_org_data(session_factory)
    row = _seed_session(session_factory, scope="clients")

    resp = client.get(f"/admin/impersonation/{row.id}/clients")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    rows = session_factory.execute(
        select(PlatformAuditLog).where(PlatformAuditLog.action == "impersonation.viewed")
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].result_row_count == 2
    assert rows[0].meta["session_id"] == str(row.id)
    assert rows[0].meta["scope"] == "clients"


def test_audit_failure_blocks_read(session_factory, monkeypatch):
    _seed_target_org_data(session_factory)
    row = _seed_session(session_factory, scope="clients")
    c = _make_client(session_factory, IDENTITY_A, monkeypatch, raise_server_exceptions=False)
    try:

        def _raise(*args, **kwargs):
            raise RuntimeError("audit write failed")

        monkeypatch.setattr(impersonation_module, "write_audit", _raise)

        resp = c.get(f"/admin/impersonation/{row.id}/clients")
        assert resp.status_code == 500
        assert "Müvekkil" not in resp.text

        audit_count = session_factory.execute(
            select(PlatformAuditLog).where(PlatformAuditLog.action == "impersonation.viewed")
        ).scalars().all()
        assert audit_count == []
    finally:
        app.dependency_overrides.clear()


def test_volume_cap_exceeded_returns_429(session_factory, monkeypatch):
    _seed_target_org_data(session_factory)
    row = _seed_session(session_factory, scope="clients")
    c = _make_client(session_factory, IDENTITY_A, monkeypatch, volume_cap=1)
    try:
        resp = c.get(f"/admin/impersonation/{row.id}/clients")
        assert resp.status_code == 429
        assert resp.json()["detail"] == "volume_cap_exceeded"
        assert resp.text.count("Müvekkil") == 0

        rows = session_factory.execute(
            select(PlatformAuditLog).where(
                PlatformAuditLog.action == "impersonation.volume_exceeded"
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].meta["session_id"] == str(row.id)

        viewed = session_factory.execute(
            select(PlatformAuditLog).where(PlatformAuditLog.action == "impersonation.viewed")
        ).scalars().all()
        assert viewed == []
    finally:
        app.dependency_overrides.clear()


def test_volume_cap_cumulative_across_sequential_requests(session_factory, monkeypatch):
    _seed_target_org_data(session_factory)
    row = _seed_session(session_factory, scope="clients")
    c = _make_client(session_factory, IDENTITY_A, monkeypatch, volume_cap=3)
    try:
        resp1 = c.get(f"/admin/impersonation/{row.id}/clients")
        assert resp1.status_code == 200
        assert len(resp1.json()) == 2

        resp2 = c.get(f"/admin/impersonation/{row.id}/clients")
        assert resp2.status_code == 429
        assert resp2.json()["detail"] == "volume_cap_exceeded"

        viewed = session_factory.execute(
            select(PlatformAuditLog).where(PlatformAuditLog.action == "impersonation.viewed")
        ).scalars().all()
        assert len(viewed) == 1
    finally:
        app.dependency_overrides.clear()


def test_dual_control_unapproved_read_403(session_factory, monkeypatch):
    _seed_target_org_data(session_factory)
    row = _seed_session(session_factory, scope="ozel_nitelikli", requires_dual_control=True)
    c = _make_client(session_factory, IDENTITY_A, monkeypatch)
    try:
        resp = c.get(f"/admin/impersonation/{row.id}/ozel_nitelikli")
        assert resp.status_code == 403

        row.approved_by = uuid.UUID(ADMIN_B_ID)
        session_factory.commit()

        resp = c.get(f"/admin/impersonation/{row.id}/ozel_nitelikli")
        assert resp.status_code == 200
        assert len(resp.json()) == 2
    finally:
        app.dependency_overrides.clear()
