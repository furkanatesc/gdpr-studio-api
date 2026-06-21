"""Hesap uçları: /api/auth/bootstrap (provision) + /api/auth/me."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..auth.identity import Identity, _claims_from_request, get_current_identity
from ..db import get_session
from ..models import Organization, User
from ..repositories import AccountRepository, InvitationRepository

router = APIRouter(prefix="/api/auth", tags=["auth"])


class BootstrapRequest(BaseModel):
    orgName: str = Field(min_length=2, max_length=255)

    @field_validator("orgName", mode="before")
    @classmethod
    def strip_and_reject_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("orgName boş olamaz.")
        return v


class IdentityOut(BaseModel):
    userId: str
    email: str
    orgId: str
    orgName: str
    role: str


def _to_out(user: User, org: Organization, role: str) -> IdentityOut:
    return IdentityOut(
        userId=str(user.id),
        email=user.email,
        orgId=str(org.id),
        orgName=org.name,
        role=role,
    )


@router.post("/bootstrap", response_model=IdentityOut)
def bootstrap(
    body: BootstrapRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> IdentityOut:
    claims = _claims_from_request(request)
    accounts = AccountRepository(session)
    invites = InvitationRepository(session)

    user = accounts.get_user_by_supabase_id(claims.sub)
    if user is None:
        user = accounts.create_user(claims.sub, claims.email)

    membership = accounts.get_membership_for_user(user.id)
    if membership is not None:  # idempotent: zaten provisioned
        org = session.get(Organization, membership.org_id)
        if org is None:
            raise HTTPException(status_code=404, detail="Hesap verisi bulunamadı.")
        return _to_out(user, org, membership.role)

    pending = invites.get_pending_by_email(claims.email)
    if pending is not None:  # davetle katıl
        membership = accounts.add_membership(user.id, pending.org_id, pending.role)
        invites.mark_accepted(pending)
        org = session.get(Organization, pending.org_id)
    else:  # yeni kurum + yönetici
        org = accounts.create_org_with_admin(body.orgName, user.id)
        membership = accounts.get_membership_for_user(user.id)

    session.commit()
    return _to_out(user, org, membership.role)


@router.get("/me", response_model=IdentityOut)
def me(
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(get_session),
) -> IdentityOut:
    user = session.get(User, identity.user_id)
    org = session.get(Organization, identity.org_id)
    if user is None or org is None:
        raise HTTPException(status_code=404, detail="Hesap verisi bulunamadı.")
    return _to_out(user, org, identity.role)
