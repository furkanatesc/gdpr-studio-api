"""İstek kimliği: JWT (veya dev-bypass) → user + org + rol. Tenant dikişinin gerçeği."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_session
from ..repositories import AccountRepository
from .jwt import AuthClaims, verify_token

_DEV_SUB = "dev-user"
_DEV_EMAIL = "dev@kvkkyonetim.local"


@dataclass(frozen=True)
class Identity:
    user_id: uuid.UUID
    org_id: uuid.UUID
    role: str
    email: str


def _claims_from_request(request: Request) -> AuthClaims:
    settings = get_settings()
    if settings.auth_dev_bypass or not settings.supabase_project_url:
        if settings.environment == "production":
            raise HTTPException(status_code=401, detail="Kimlik doğrulama gerekli.")
        return AuthClaims(sub=_DEV_SUB, email=_DEV_EMAIL)
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Oturum bulunamadı.")
    return verify_token(auth[7:])


def get_current_identity(
    request: Request,
    session: Session = Depends(get_session),
) -> Identity:
    claims = _claims_from_request(request)
    # Kimlik çözümü doğası gereği org-ötesi bir okumadır: kullanıcının HANGİ org'a
    # ait olduğunu bulmadan app.current_org_id set edilemez (set edilecek değer budur).
    # FORCE RLS altında (non-superuser uygulama rolü) bu üyelik okuması bypass GUC
    # olmadan fail-closed döner → her uç patlar. Bu yüzden YALNIZ bu okuma için
    # transaction-local bypass açıp HEMEN kapatırız; böylece sonraki tenant
    # erişimleri (tenant_session'ın set ettiği app.current_org_id ile) izole kalır.
    # Yerel import: tenant_session bu modülü import eder (döngüyü kırmak için).
    from .tenant_session import begin_provisioning, end_provisioning

    accounts = AccountRepository(session)
    begin_provisioning(session)
    try:
        user = accounts.get_user_by_supabase_id(claims.sub)
        membership = accounts.get_membership_for_user(user.id) if user is not None else None
    finally:
        end_provisioning(session)
    if user is None:
        raise HTTPException(status_code=403, detail="Önce kurum oluşturun (kayıt tamamlanmamış).")
    if membership is None:
        raise HTTPException(status_code=403, detail="Bir kuruma ait değilsiniz.")
    return Identity(user_id=user.id, org_id=membership.org_id, role=membership.role, email=user.email)


def require_role(role: str):
    def _dep(identity: Identity = Depends(get_current_identity)) -> Identity:
        if identity.role != role:
            raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok.")
        return identity

    return _dep
