"""DSAR (H3-2) — hesap verisi export (JSON) + erasure (soft-delete). Yalnız yönetici.

KVKK m.11/m.17 · GDPR m.15/m.17. Part 1: export + soft-delete + fail-closed.
Gerçek purge (14 gün sonra hard-delete + Supabase auth silme) Part 2'de.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..audit import record_audit
from ..auth.identity import Identity, require_role
from ..auth.tenant_session import tenant_session
from ..models import (
    AuditLog,
    Client,
    ClientDocument,
    ClientDocumentVersion,
    ClientProcessor,
    ComplianceStatus,
    GeneratedDocument,
    Invitation,
    Membership,
    Organization,
    Process,
    Subscription,
    UsageCounter,
    User,
)

router = APIRouter(prefix="/api/dsar", tags=["dsar"])


def _val(v: Any) -> Any:
    if isinstance(v, uuid.UUID):
        return str(v)
    if isinstance(v, datetime):
        return v.isoformat()
    return v


def _row(obj: Any) -> dict[str, Any]:
    return {c.key: _val(getattr(obj, c.key)) for c in obj.__mapper__.column_attrs}


def _rows(session: Session, model: Any, org_id: uuid.UUID) -> list[dict[str, Any]]:
    return [_row(o) for o in session.scalars(select(model).where(model.org_id == org_id))]


class EraseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Yanlışlıkla silmeyi önler: yönetici kurum adını birebir yazmalı.
    confirm: str


@router.get("/export")
def export_account(
    identity: Identity = Depends(require_role("yonetici")),
    session: Session = Depends(tenant_session),
) -> Response:
    org = session.get(Organization, identity.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Kurum bulunamadı.")

    member_ids = list(
        session.scalars(select(Membership.user_id).where(Membership.org_id == identity.org_id))
    )
    users = (
        session.scalars(select(User).where(User.id.in_(member_ids))) if member_ids else []
    )

    data: dict[str, Any] = {
        "exportedAt": datetime.now().astimezone().isoformat(),
        "organization": _row(org),
        "users": [{"id": str(u.id), "email": u.email} for u in users],
        "memberships": _rows(session, Membership, identity.org_id),
        "invitations": _rows(session, Invitation, identity.org_id),
        "clients": _rows(session, Client, identity.org_id),
        "clientDocuments": _rows(session, ClientDocument, identity.org_id),
        "clientDocumentVersions": _rows(session, ClientDocumentVersion, identity.org_id),
        "clientProcessors": _rows(session, ClientProcessor, identity.org_id),
        "complianceStatus": _rows(session, ComplianceStatus, identity.org_id),
        "generatedDocuments": _rows(session, GeneratedDocument, identity.org_id),
        "subscriptions": _rows(session, Subscription, identity.org_id),
        "usageCounters": _rows(session, UsageCounter, identity.org_id),
        "processes": _rows(session, Process, identity.org_id),
        "auditLogs": _rows(session, AuditLog, identity.org_id),
    }

    record_audit(
        session, org_id=identity.org_id, action="dsar.export",
        actor_user_id=identity.user_id, target_type="org", target_id=str(identity.org_id),
    )
    session.commit()

    body = json.dumps(data, ensure_ascii=False, indent=2)
    filename = f"kvkk-export-{identity.org_id}.json"
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/erase")
def erase_account(
    body: EraseRequest,
    identity: Identity = Depends(require_role("yonetici")),
    session: Session = Depends(tenant_session),
) -> dict[str, Any]:
    org = session.get(Organization, identity.org_id)
    if org is None:
        raise HTTPException(status_code=404, detail="Kurum bulunamadı.")
    if body.confirm.strip() != org.name:
        raise HTTPException(status_code=422, detail="Onay için kurum adını birebir yazın.")

    org.status = "deleting"
    org.deleted_at = datetime.now().astimezone()
    record_audit(
        session, org_id=identity.org_id, action="org.erasure_requested",
        actor_user_id=identity.user_id, target_type="org", target_id=str(identity.org_id),
    )
    session.commit()
    return {
        "status": "deleting",
        "deletedAt": org.deleted_at.isoformat(),
        "message": "Hesap kapatıldı; erişim durduruldu. Veriler 14 gün içinde kalıcı silinecek.",
    }
