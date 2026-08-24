"""Impersonation session yaşam döngüsü — H5_LEGAL_READY kapısı, dual-control, fail-closed audit.

sqlite: RLS/kolon-bazlı GRANT (approved_by) burada GÖRÜNMEZ — bkz. PG-gated
`test_admin_impersonation_rls.py`. Bu dosya sadece uç/repository davranışını test eder.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import admin_api.modules.impersonation as impersonation_module
import admin_api.repositories as repositories_module
from admin_api.auth import PlatformAdminIdentity, require_platform_admin
from admin_api.config import AdminSettings
from admin_api.db import admin_session
from admin_api.main import app
from admin_api.modules.impersonation import resolve_active_session
from admin_api.repositories import ImpersonationRepository
from app.db import Base
from app.models import ImpersonationSession, PlatformAdmin, PlatformAuditLog

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


def _make_client(session, identity, legal_ready, monkeypatch) -> TestClient:
    def _override_session():
        yield session

    app.dependency_overrides[require_platform_admin] = lambda: identity
    app.dependency_overrides[admin_session] = _override_session
    monkeypatch.setattr(
        impersonation_module,
        "get_admin_settings",
        lambda: AdminSettings(h5_legal_ready=legal_ready),
    )
    return TestClient(app)


@pytest.fixture()
def client_legal_off(session_factory, monkeypatch):
    c = _make_client(session_factory, IDENTITY_A, False, monkeypatch)
    yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def client_legal_on(session_factory, monkeypatch):
    c = _make_client(session_factory, IDENTITY_A, True, monkeypatch)
    yield c
    app.dependency_overrides.clear()


def _start_body(scope: str = "documents") -> dict:
    return {"targetOrgId": str(TARGET_ORG), "reason": "inceleme", "scope": scope}


def test_start_blocked_when_legal_flag_off(client_legal_off):
    resp = client_legal_off.post("/admin/impersonation", json=_start_body())
    assert resp.status_code == 403
    assert resp.json()["detail"] == "h5_legal_not_ready"


def test_start_requires_reason_and_scope(client_legal_on):
    resp = client_legal_on.post(
        "/admin/impersonation", json={"targetOrgId": str(TARGET_ORG), "reason": "inceleme"}
    )
    assert resp.status_code == 422


def test_start_creates_session_and_audit(client_legal_on, session_factory):
    resp = client_legal_on.post("/admin/impersonation", json=_start_body("documents"))
    assert resp.status_code == 201
    body = resp.json()
    assert body["requiresDualControl"] is False

    rows = session_factory.execute(
        select(PlatformAuditLog).where(PlatformAuditLog.action == "impersonation.started")
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].target_org_id == TARGET_ORG


def test_special_category_scope_requires_approval(client_legal_on):
    resp = client_legal_on.post("/admin/impersonation", json=_start_body("ozel_nitelikli"))
    assert resp.status_code == 201
    assert resp.json()["requiresDualControl"] is True


def test_approve_rejects_self_approval(client_legal_on):
    start = client_legal_on.post("/admin/impersonation", json=_start_body("ozel_nitelikli"))
    session_id = start.json()["id"]

    resp = client_legal_on.post(f"/admin/impersonation/{session_id}/approve")
    assert resp.status_code == 403
    assert resp.json()["detail"] == "self_approval_forbidden"


def test_approve_by_second_admin_sets_approved_by(client_legal_on, session_factory):
    start = client_legal_on.post("/admin/impersonation", json=_start_body("ozel_nitelikli"))
    session_id = start.json()["id"]

    app.dependency_overrides[require_platform_admin] = lambda: IDENTITY_B
    resp = client_legal_on.post(f"/admin/impersonation/{session_id}/approve")
    assert resp.status_code == 200
    assert resp.json()["approvedBy"] == ADMIN_B_ID

    rows = session_factory.execute(
        select(PlatformAuditLog).where(PlatformAuditLog.action == "impersonation.approved")
    ).scalars().all()
    assert len(rows) == 1


def test_resolve_active_session_rejects_expired(session_factory):
    row = ImpersonationSession(
        platform_admin_id=uuid.UUID(ADMIN_A_ID),
        target_org_id=TARGET_ORG,
        reason="inceleme",
        scope="documents",
        requires_dual_control=False,
        bound_sub="sub-a",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    session_factory.add(row)
    session_factory.commit()

    with pytest.raises(HTTPException) as exc:
        resolve_active_session(session_factory, IDENTITY_A, row.id, "sub-a")
    assert exc.value.status_code == 403


def test_resolve_active_session_rejects_unapproved_dual_control(session_factory):
    row = ImpersonationSession(
        platform_admin_id=uuid.UUID(ADMIN_A_ID),
        target_org_id=TARGET_ORG,
        reason="inceleme",
        scope="ozel_nitelikli",
        requires_dual_control=True,
        bound_sub="sub-a",
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    session_factory.add(row)
    session_factory.commit()

    with pytest.raises(HTTPException) as exc:
        resolve_active_session(session_factory, IDENTITY_A, row.id, "sub-a")
    assert exc.value.status_code == 403

    row.approved_by = uuid.UUID(ADMIN_B_ID)
    session_factory.commit()

    resolved = resolve_active_session(session_factory, IDENTITY_A, row.id, "sub-a")
    assert resolved.id == row.id


def test_end_sets_ended_at_and_kind(client_legal_on, session_factory):
    start = client_legal_on.post("/admin/impersonation", json=_start_body("documents"))
    session_id = start.json()["id"]

    resp = client_legal_on.delete(f"/admin/impersonation/{session_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["endKind"] == "manual"
    assert body["endedAt"] is not None

    rows = session_factory.execute(
        select(PlatformAuditLog).where(PlatformAuditLog.action == "impersonation.ended")
    ).scalars().all()
    assert len(rows) == 1


def _seed_active_session(
    session_factory, *, admin_id: str = ADMIN_A_ID, bound_sub: str = "sub-a"
) -> ImpersonationSession:
    row = ImpersonationSession(
        platform_admin_id=uuid.UUID(admin_id),
        target_org_id=TARGET_ORG,
        reason="inceleme",
        scope="documents",
        requires_dual_control=False,
        bound_sub=bound_sub,
        expires_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    session_factory.add(row)
    session_factory.commit()
    return row


def test_resolve_rejects_wrong_owner(session_factory):
    row = _seed_active_session(session_factory)

    with pytest.raises(HTTPException) as exc:
        resolve_active_session(session_factory, IDENTITY_B, row.id, "sub-a")
    assert exc.value.status_code == 403


def test_resolve_rejects_bound_sub_mismatch(session_factory):
    row = _seed_active_session(session_factory)

    with pytest.raises(HTTPException) as exc:
        resolve_active_session(session_factory, IDENTITY_A, row.id, "sub-DIFFERENT")
    assert exc.value.status_code == 403


def test_resolve_rejects_inactive_admin(session_factory):
    row = _seed_active_session(session_factory)

    admin_row = session_factory.get(PlatformAdmin, uuid.UUID(ADMIN_A_ID))
    admin_row.is_active = False
    session_factory.commit()

    with pytest.raises(HTTPException) as exc:
        resolve_active_session(session_factory, IDENTITY_A, row.id, "sub-a")
    assert exc.value.status_code == 403

    admin_row.is_active = True
    session_factory.commit()

    resolved = resolve_active_session(session_factory, IDENTITY_A, row.id, "sub-a")
    assert resolved.id == row.id


def test_resolve_happy_path_returns_session(session_factory):
    row = _seed_active_session(session_factory)

    resolved = resolve_active_session(session_factory, IDENTITY_A, row.id, "sub-a")
    assert resolved.id == row.id


def test_start_is_fail_closed_when_audit_raises(session_factory, monkeypatch):
    engine = session_factory.bind

    def _raise_write_audit(*args, **kwargs):
        raise RuntimeError("audit write failed")

    monkeypatch.setattr(repositories_module, "write_audit", _raise_write_audit)

    with pytest.raises(RuntimeError):
        ImpersonationRepository(session_factory).start(
            IDENTITY_A, TARGET_ORG, "inceleme", "documents"
        )

    # admin_session()'daki gerçek teardown yolunu birebir taklit et: yalnızca close(),
    # açık rollback YOK (bkz. admin_api/db.py) — flush edilmiş ama commit edilmemiş
    # insert'in hayatta kalmadığını kanıtlar.
    session_factory.close()

    fresh = sessionmaker(bind=engine, future=True)()
    try:
        count = fresh.execute(
            select(func.count()).select_from(ImpersonationSession)
        ).scalar_one()
        assert count == 0
    finally:
        fresh.close()


def test_start_legal_off_creates_no_rows(client_legal_off, session_factory):
    resp = client_legal_off.post("/admin/impersonation", json=_start_body())
    assert resp.status_code == 403
    assert resp.json()["detail"] == "h5_legal_not_ready"

    session_count = session_factory.execute(
        select(func.count()).select_from(ImpersonationSession)
    ).scalar_one()
    assert session_count == 0

    audit_count = session_factory.execute(
        select(func.count())
        .select_from(PlatformAuditLog)
        .where(PlatformAuditLog.action == "impersonation.started")
    ).scalar_one()
    assert audit_count == 0
