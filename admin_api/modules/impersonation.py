"""Impersonation session yaşam döngüsü — H5_LEGAL_READY kapısı + dual-control + fail-closed audit.

Yaşam döngüsü: start/approve/end + `resolve_active_session`. Kapsamlı kiracı okuma proxy'si
(`GET /admin/impersonation/{session_id}/{scope}`) Task 9'da eklendi — METADATA-ONLY
`SCOPE_READERS` kayıt defteri, bypass-off assert, erişim-başı fail-closed audit, hacim sınırı.
Okuma yolunda `begin_provisioning`/bypass YOK — yalnız tek-org `set_org_context`.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.auth.tenant_session import set_org_context
from app.models import (
    Client,
    ClientProcessor,
    ComplianceStatus,
    GeneratedDocument,
    ImpersonationSession,
    PlatformAuditLog,
)

from ..audit import write_audit
from ..auth import PlatformAdminIdentity, require_platform_admin
from ..config import get_admin_settings
from ..db import admin_session, assert_bypass_off
from ..repositories import ImpersonationRepository
from ..repositories import resolve_active_session as resolve_active_session

router = APIRouter(prefix="/admin/impersonation", tags=["admin-impersonation"])

__all__ = ["router", "resolve_active_session", "SCOPE_READERS"]


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ImpersonationStartRequest(_Camel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    target_org_id: uuid.UUID
    reason: str
    scope: str


class ImpersonationSessionResponse(_Camel):
    id: uuid.UUID
    platform_admin_id: uuid.UUID
    target_org_id: uuid.UUID
    reason: str
    scope: str
    requires_dual_control: bool
    approved_by: uuid.UUID | None
    bound_sub: str
    started_at: datetime
    expires_at: datetime
    ended_at: datetime | None
    end_kind: str | None

    @classmethod
    def from_row(cls, row: ImpersonationSession) -> ImpersonationSessionResponse:
        return cls(
            id=row.id,
            platform_admin_id=row.platform_admin_id,
            target_org_id=row.target_org_id,
            reason=row.reason,
            scope=row.scope,
            requires_dual_control=row.requires_dual_control,
            approved_by=row.approved_by,
            bound_sub=row.bound_sub,
            started_at=row.started_at,
            expires_at=row.expires_at,
            ended_at=row.ended_at,
            end_kind=row.end_kind,
        )


class ImpersonationSessionPage(_Camel):
    items: list[ImpersonationSessionResponse]
    next_cursor: str | None


_MAX_LIST_LIMIT = 200


@router.get("", response_model=ImpersonationSessionPage)
def list_impersonation(
    cursor: str | None = None,
    limit: int = 50,
    identity: PlatformAdminIdentity = Depends(require_platform_admin),
    session: Session = Depends(admin_session),
) -> ImpersonationSessionPage:
    # Legal-gate YOK: dönen şey oturum metadata'sı (kiracı verisi değil); onaylayıcının
    # başka admin'in bekleyen oturumunu görebilmesi için platform-geneli (audit gibi).
    if not (1 <= limit <= _MAX_LIST_LIMIT):
        raise HTTPException(status_code=422, detail="invalid_limit")
    try:
        page = ImpersonationRepository(session).list(cursor=cursor, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="malformed_cursor") from exc
    return ImpersonationSessionPage(
        items=[ImpersonationSessionResponse.from_row(row) for row in page["items"]],
        next_cursor=page["next_cursor"],
    )


@router.post("", response_model=ImpersonationSessionResponse, status_code=201)
def start_impersonation(
    body: ImpersonationStartRequest,
    identity: PlatformAdminIdentity = Depends(require_platform_admin),
    session: Session = Depends(admin_session),
) -> ImpersonationSessionResponse:
    if not get_admin_settings().h5_legal_ready:
        raise HTTPException(status_code=403, detail="h5_legal_not_ready")
    # Yalnız okunabilir scope'lar: read-proxy SCOPE_READERS dışını 404'ler → geçersiz
    # scope'lu oturum ölü doğar. Start'ta reddet (backend = scope'ta otorite kaynak).
    if body.scope not in SCOPE_READERS:
        raise HTTPException(status_code=422, detail="unknown_scope")
    row = ImpersonationRepository(session).start(
        identity, body.target_org_id, body.reason, body.scope
    )
    return ImpersonationSessionResponse.from_row(row)


@router.post("/{session_id}/approve", response_model=ImpersonationSessionResponse)
def approve_impersonation(
    session_id: uuid.UUID,
    identity: PlatformAdminIdentity = Depends(require_platform_admin),
    session: Session = Depends(admin_session),
) -> ImpersonationSessionResponse:
    row = ImpersonationRepository(session).approve(identity, session_id)
    return ImpersonationSessionResponse.from_row(row)


@router.delete("/{session_id}", response_model=ImpersonationSessionResponse)
def end_impersonation(
    session_id: uuid.UUID,
    identity: PlatformAdminIdentity = Depends(require_platform_admin),
    session: Session = Depends(admin_session),
) -> ImpersonationSessionResponse:
    row = ImpersonationRepository(session).end(identity, session_id)
    return ImpersonationSessionResponse.from_row(row)


def _read_clients(session: Session, org_id: uuid.UUID) -> list[dict]:
    rows = session.execute(
        select(Client.id, Client.name, Client.sector, Client.created_at).where(
            Client.org_id == org_id
        )
    ).all()
    return [
        {"id": r.id, "name": r.name, "sector": r.sector, "createdAt": r.created_at} for r in rows
    ]


def _read_compliance(session: Session, org_id: uuid.UUID) -> list[dict]:
    rows = session.execute(
        select(ComplianceStatus.requirement_key, ComplianceStatus.status).where(
            ComplianceStatus.org_id == org_id
        )
    ).all()
    return [{"requirementKey": r.requirement_key, "status": r.status} for r in rows]


def _read_documents_meta(session: Session, org_id: uuid.UUID) -> list[dict]:
    rows = session.execute(
        select(
            GeneratedDocument.id, GeneratedDocument.doc_type, GeneratedDocument.created_at
        ).where(GeneratedDocument.org_id == org_id)
    ).all()
    return [{"id": r.id, "docType": r.doc_type, "createdAt": r.created_at} for r in rows]


def _read_ozel_nitelikli(session: Session, org_id: uuid.UUID) -> list[dict]:
    # v1 approximation: schema has no dedicated KVKK m.6 special-category flag column yet —
    # this scope's data-processor relationships are the closest DPA-sensitive analog available.
    # Still metadata-only (id/client_id/ad — no aktarim_aliases/notlar/adres/iletisim).
    rows = session.execute(
        select(ClientProcessor.id, ClientProcessor.client_id, ClientProcessor.ad).where(
            ClientProcessor.org_id == org_id
        )
    ).all()
    return [{"id": r.id, "clientId": r.client_id, "ad": r.ad} for r in rows]


SCOPE_READERS: dict[str, Callable[[Session, uuid.UUID], list[dict]]] = {
    "clients": _read_clients,
    "compliance": _read_compliance,
    "documents_meta": _read_documents_meta,
    "ozel_nitelikli": _read_ozel_nitelikli,
}


def _cumulative_prior_rows(session: Session, session_id: uuid.UUID, target_org_id: uuid.UUID) -> int:
    """Prior `impersonation.viewed` row counts for THIS session (Python-side filter on `meta`
    — avoids Postgres/sqlite JSON-operator dialect divergence for a per-request, small scan)."""
    prior = session.execute(
        select(PlatformAuditLog.result_row_count, PlatformAuditLog.meta).where(
            PlatformAuditLog.action == "impersonation.viewed",
            PlatformAuditLog.target_org_id == target_org_id,
        )
    ).all()
    return sum(
        (count or 0)
        for count, meta in prior
        if meta is not None and meta.get("session_id") == str(session_id)
    )


@router.get("/{session_id}/{scope}")
def read_impersonated_scope(
    session_id: uuid.UUID,
    scope: str,
    identity: PlatformAdminIdentity = Depends(require_platform_admin),
    session: Session = Depends(admin_session),
) -> list[dict]:
    if not get_admin_settings().h5_legal_ready:
        raise HTTPException(status_code=403, detail="h5_legal_not_ready")

    sess = resolve_active_session(session, identity, session_id, token_sub=identity.token_sub)

    assert_bypass_off(session)

    if session.bind.dialect.name == "postgresql":
        # Serialize concurrent reads on the SAME session so the volume-cap check + the viewed-audit
        # write are atomic (else two concurrent reads can jointly exceed the cap — spec §4.3 makes the
        # row cap the primary exfil control). xact lock auto-releases at write_audit's commit.
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext('impersonation_read'), hashtext(:sid))"),
            {"sid": str(session_id)},
        )

    if scope not in SCOPE_READERS:
        raise HTTPException(status_code=404, detail="unknown_scope")
    if scope != sess.scope:
        raise HTTPException(status_code=403, detail="scope_mismatch")

    set_org_context(session, sess.target_org_id)

    rows = SCOPE_READERS[scope](session, sess.target_org_id)

    cumulative = _cumulative_prior_rows(session, session_id, sess.target_org_id) + len(rows)
    if cumulative > get_admin_settings().impersonation_volume_cap:
        write_audit(
            session,
            actor=identity,
            action="impersonation.volume_exceeded",
            reason=sess.reason,
            target_org_id=sess.target_org_id,
            target_type=scope,
            meta={"session_id": str(session_id), "scope": scope},
        )
        raise HTTPException(status_code=429, detail="volume_cap_exceeded")

    # Fail-closed hard precondition: write_audit flushes+commits internally (bkz. admin_api.audit).
    # If it raises, no response is built below — data is NEVER serialized without a committed audit row.
    write_audit(
        session,
        actor=identity,
        action="impersonation.viewed",
        reason=sess.reason,
        target_org_id=sess.target_org_id,
        target_type=scope,
        result_row_count=len(rows),
        meta={"session_id": str(session_id), "scope": scope},
    )

    return rows
