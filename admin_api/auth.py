"""Platform-admin JWT doğrulama — kiracı `app.auth.jwt`'den AYRI JWKS/issuer/aud, AAL2 fail-closed.

Ayrı Supabase staff projesi ile kimliklenir; `aud=platform-admin` (kiracı `authenticated` REDDEDİLİR).
Her istekte `platform_admins.is_active` DB'den yeniden kontrol edilir (token deprovision'ı geçersiz kılmaz).
"""

from __future__ import annotations

from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request
from jwt import PyJWKClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PlatformAdmin

from .config import get_admin_settings
from .db import admin_session

_jwks: PyJWKClient | None = None


def _jwks_client() -> PyJWKClient:
    global _jwks
    if _jwks is None:  # SEPARATE instance — never reuse app.auth.jwt singleton
        s = get_admin_settings()
        _jwks = PyJWKClient(s.admin_jwks_url, timeout=s.admin_jwks_timeout_s)
    return _jwks


def _verify(token: str) -> dict:
    s = get_admin_settings()
    key = _jwks_client().get_signing_key_from_jwt(token).key
    return jwt.decode(
        token,
        key,
        algorithms=["RS256", "ES256"],
        audience=s.admin_supabase_jwt_aud,
        issuer=s.admin_supabase_issuer,
        leeway=60,
        options={"require": ["sub", "iss", "aud"]},
    )


def _require_aal2(claims: dict) -> None:
    if claims.get("aal") != "aal2":
        raise HTTPException(status_code=403, detail="mfa_required")


@dataclass(frozen=True)
class PlatformAdminIdentity:
    admin_id: str
    supabase_user_id: str
    email: str
    token_sub: str


def _identity_from_claims(claims: dict, session: Session) -> PlatformAdminIdentity:
    if claims.get("aud") != get_admin_settings().admin_supabase_jwt_aud:
        raise HTTPException(status_code=401, detail="invalid_audience")
    _require_aal2(claims)
    row = session.execute(
        select(PlatformAdmin).where(
            PlatformAdmin.supabase_user_id == claims["sub"],
            PlatformAdmin.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=403, detail="not_platform_admin")
    return PlatformAdminIdentity(str(row.id), row.supabase_user_id, row.email, claims["sub"])


def require_platform_admin(
    request: Request, session: Session = Depends(admin_session)
) -> PlatformAdminIdentity:
    hdr = request.headers.get("authorization", "")
    if not hdr.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing_token")
    try:
        claims = _verify(hdr[7:])
    except Exception as e:  # imza/aud/expiry → 401 (detay loglanmaz)
        raise HTTPException(status_code=401, detail="invalid_token") from e
    return _identity_from_claims(claims, session)
