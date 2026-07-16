"""Üye yönetimi uçları — listele (üye) / rol değiştir / çıkar (yönetici).

Mimari review H2: ayrılan avukatın uyum verisine erişimi süresizdi (offboarding yoktu) ve
yönetici mevcut üyeleri arayüzden yönetemiyordu. Bu modül boşluğu kapatır.

Kritik güvenceler:
- **Son-yönetici koruması:** son `yonetici`'yi düşürmek veya çıkarmak 409 → kurum yönetimsiz
  kalamaz (self-lockout dahil).
- Rol değiştir/çıkar **yalnız yönetici**; liste her üyeye açık (ekip rosterı).
- Tüm sorgular RLS + açık org_id koşulu altında → çapraz-kiracı erişim yok.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from ..auth.identity import Identity, get_current_identity, require_role
from ..auth.tenant_session import tenant_session
from ..repositories import MembershipRepository

router = APIRouter(prefix="/api/memberships", tags=["memberships"])

_ROLES = {"yonetici", "avukat"}


class MemberOut(BaseModel):
    userId: str
    email: str
    role: str
    isSelf: bool


class RoleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str


def _to_out(member, user, self_user_id: uuid.UUID) -> MemberOut:
    return MemberOut(
        userId=str(user.id),
        email=user.email,
        role=member.role,
        isSelf=user.id == self_user_id,
    )


@router.get("", response_model=list[MemberOut])
def list_members(
    session: Session = Depends(tenant_session),
    identity: Identity = Depends(get_current_identity),
) -> list[MemberOut]:
    repo = MembershipRepository(session)
    return [_to_out(m, u, identity.user_id) for m, u in repo.list_members(identity.org_id)]


@router.patch("/{user_id}", response_model=MemberOut)
def update_member_role(
    user_id: uuid.UUID,
    body: RoleUpdate,
    session: Session = Depends(tenant_session),
    identity: Identity = Depends(require_role("yonetici")),
) -> MemberOut:
    if body.role not in _ROLES:
        raise HTTPException(status_code=422, detail="Geçersiz rol.")
    repo = MembershipRepository(session)
    member = repo.get_member(identity.org_id, user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Üye bulunamadı.")

    # Son yöneticiyi avukata düşürme → kurum yönetimsiz kalır (self-lockout dahil).
    if member.role == "yonetici" and body.role != "yonetici":
        if repo.count_role(identity.org_id, "yonetici") <= 1:
            raise HTTPException(
                status_code=409,
                detail={"code": "last_admin", "message": "Son yöneticinin rolü değiştirilemez."},
            )

    repo.set_role(member, body.role)
    session.commit()
    # user bilgisini tekrar çekmemek için: e-postayı listeden değil, hafif okuma ile döneriz.
    from ..models import User

    user = session.get(User, user_id)
    return _to_out(member, user, identity.user_id)


@router.delete("/{user_id}", status_code=204)
def remove_member(
    user_id: uuid.UUID,
    session: Session = Depends(tenant_session),
    identity: Identity = Depends(require_role("yonetici")),
) -> Response:
    repo = MembershipRepository(session)
    member = repo.get_member(identity.org_id, user_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Üye bulunamadı.")

    # Son yöneticiyi çıkarma → kurum yönetimsiz kalır (kendini de kapsar).
    if member.role == "yonetici" and repo.count_role(identity.org_id, "yonetici") <= 1:
        raise HTTPException(
            status_code=409,
            detail={"code": "last_admin", "message": "Son yönetici kurumdan çıkarılamaz."},
        )

    repo.remove(member)
    session.commit()
    return Response(status_code=204)
