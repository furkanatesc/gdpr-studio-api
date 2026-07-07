"""Davet uçları — oluştur/listele/iptal (yönetici) + kabul (kimlik)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr
from sqlalchemy.orm import Session

from ..auth.identity import Identity, _claims_from_request, require_role
from ..auth.tenant_session import begin_provisioning, tenant_session
from ..config import get_settings
from ..db import get_session
from ..email.sender import EmailMessage, get_email_sender
from ..invites.tokens import InviteExpired, InviteInvalid, make_invite_token, read_invite_token
from ..models import Organization
from ..repositories import AccountRepository, InvitationRepository

_log = logging.getLogger("app.invitations")

router = APIRouter(prefix="/api/invitations", tags=["invitations"])

_ROLES = {"yonetici", "avukat"}


class InviteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    role: str


class InviteOut(BaseModel):
    id: str
    email: str
    role: str
    status: str
    token: str


@router.post("", status_code=201, response_model=InviteOut)
def create_invitation(
    body: InviteRequest,
    session: Session = Depends(tenant_session),
    identity: Identity = Depends(require_role("yonetici")),
) -> InviteOut:
    if body.role not in _ROLES:
        raise HTTPException(status_code=422, detail="Geçersiz rol.")
    settings = get_settings()
    token = make_invite_token(str(identity.org_id), str(body.email))
    exp = datetime.now(UTC) + timedelta(hours=settings.invite_ttl_hours)
    invs = InvitationRepository(session)
    inv = invs.create(identity.org_id, str(body.email), body.role, token, exp, identity.user_id)
    session.commit()

    link = f"{settings.app_base_url.rstrip('/')}/davet/{token}"
    try:
        get_email_sender().send(
            EmailMessage(
                to=str(body.email),
                subject="KVKK Yönetim — kurum davetiniz",
                html=f'<p>Bir kuruma davet edildiniz. Katılmak için: <a href="{link}">{link}</a></p>',
            )
        )
    except Exception:
        _log.warning("Davet e-postası gönderilemedi: %s", body.email)
    return InviteOut(id=str(inv.id), email=inv.email, role=inv.role, status=inv.status, token=token)


@router.get("", response_model=list[InviteOut])
def list_invitations(
    session: Session = Depends(tenant_session),
    identity: Identity = Depends(require_role("yonetici")),
) -> list[InviteOut]:
    invs = InvitationRepository(session).list_pending(identity.org_id)
    return [InviteOut(id=str(i.id), email=i.email, role=i.role, status=i.status, token=i.token) for i in invs]


@router.delete("/{inv_id}", status_code=204)
def revoke_invitation(
    inv_id: uuid.UUID,
    session: Session = Depends(tenant_session),
    identity: Identity = Depends(require_role("yonetici")),
) -> Response:
    ok = InvitationRepository(session).revoke(inv_id, identity.org_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Davet bulunamadı veya zaten işlenmiş.")
    session.commit()
    return Response(status_code=204)


@router.post("/{token}/accept")
def accept_invitation(
    token: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    try:
        data = read_invite_token(token)
    except InviteExpired:
        raise HTTPException(status_code=410, detail="Davetin süresi dolmuş.") from None
    except InviteInvalid:
        raise HTTPException(status_code=404, detail="Davet geçersiz.") from None

    begin_provisioning(session)  # org-ötesi okuma (davet + üyelik-var-mı) için bypass-RLS
    invs = InvitationRepository(session)
    inv = invs.get_by_token(token)
    if inv is None or inv.status != "pending":
        raise HTTPException(status_code=409, detail="Davet zaten işlenmiş.")

    claims = _claims_from_request(request)
    if claims.email.lower() != data["email"].lower():
        raise HTTPException(status_code=403, detail="Davet bu e-posta için değil.")

    accounts = AccountRepository(session)
    user = accounts.get_user_by_supabase_id(claims.sub) or accounts.create_user(claims.sub, claims.email)
    if accounts.get_membership_for_user(user.id) is not None:
        raise HTTPException(status_code=409, detail="Zaten bir kuruma üyesiniz.")

    accounts.add_membership(user.id, inv.org_id, inv.role)
    invs.mark_accepted(inv)
    # org okuması commit'ten ÖNCE: commit'te bypass GUC sıfırlanır, sonrası fail-closed olur.
    org = session.get(Organization, inv.org_id)
    session.commit()

    return {
        "userId": str(user.id),
        "email": user.email,
        "orgId": str(org.id),
        "orgName": org.name,
        "role": inv.role,
    }
