"""Platform-admin JWT doğrulama — kiracı `app.auth.jwt`'den AYRI JWKS/issuer/aud, AAL2 fail-closed.

Ayrı Supabase staff projesi ile kimliklenir; `aud=platform-admin` (kiracı `authenticated` REDDEDİLİR).
Her istekte `platform_admins.is_active` DB'den yeniden kontrol edilir (token deprovision'ı geçersiz kılmaz).
"""

from __future__ import annotations

import time
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


# MFA factor types (spec §4.2). Method may be prefixed by GoTrue (e.g. "mfa/totp"),
# so only the factor after the last "/" is matched. `password`/`otp`/`oauth`/`magiclink`
# are NOT MFA factors and never satisfy the step-up on their own.
_MFA_METHODS = frozenset({"totp", "phone", "webauthn"})
_CLOCK_SKEW_S = 60  # tolerate minor forward clock skew on the factor timestamp


def _is_mfa_method(method: object) -> bool:
    if not isinstance(method, str):
        return False
    return method.lower().rsplit("/", 1)[-1] in _MFA_METHODS


def _require_mfa(claims: dict, *, now: float | None = None) -> None:
    """Fail-closed step-up check (spec §4.2): require aal2 AND a *recent* MFA factor in
    `amr`. Missing/aal1/unknown → 401 (not 403): the caller is treated as unauthenticated
    for the admin surface until it presents a fresh MFA proof."""
    if claims.get("aal") != "aal2":
        raise HTTPException(status_code=401, detail="mfa_required")
    amr = claims.get("amr")
    if not isinstance(amr, list):
        raise HTTPException(status_code=401, detail="mfa_required")
    max_age = get_admin_settings().admin_amr_mfa_max_age_s
    now = time.time() if now is None else now
    for entry in amr:
        if not isinstance(entry, dict) or not _is_mfa_method(entry.get("method")):
            continue
        ts = entry.get("timestamp")
        if isinstance(ts, (int, float)) and not isinstance(ts, bool):
            if -_CLOCK_SKEW_S <= now - ts <= max_age:  # recent MFA factor
                return
    raise HTTPException(status_code=401, detail="mfa_required")


@dataclass(frozen=True)
class PlatformAdminIdentity:
    admin_id: str
    supabase_user_id: str
    email: str
    token_sub: str


def _identity_from_claims(claims: dict, session: Session) -> PlatformAdminIdentity:
    if claims.get("aud") != get_admin_settings().admin_supabase_jwt_aud:
        raise HTTPException(status_code=401, detail="invalid_audience")
    _require_mfa(claims)
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
