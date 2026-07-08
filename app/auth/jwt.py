"""Supabase JWT doğrulama (JWKS, asimetrik). Env-gated; secret loglanmaz."""

from __future__ import annotations

import jwt as pyjwt
from fastapi import HTTPException
from jwt import PyJWKClient
from pydantic import BaseModel

from ..config import get_settings

# Sunucu ile IdP arası saat kaymasına tolerans (iat/exp/nbf); saniye.
_CLOCK_SKEW_LEEWAY_S = 60


class AuthClaims(BaseModel):
    sub: str
    email: str = ""


_jwks_client: PyJWKClient | None = None


def reset_jwks_cache() -> None:
    global _jwks_client
    _jwks_client = None


def _signing_key_for(token: str) -> pyjwt.PyJWK:
    global _jwks_client
    if _jwks_client is None:
        url = get_settings().supabase_jwks_url
        if not url:
            raise HTTPException(status_code=401, detail="Kimlik doğrulama yapılandırılmamış.")
        _jwks_client = PyJWKClient(url)
    return _jwks_client.get_signing_key_from_jwt(token)


def verify_token(token: str) -> AuthClaims:
    settings = get_settings()
    try:
        signing_key = _signing_key_for(token)
        payload = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=settings.supabase_jwt_aud,
            leeway=_CLOCK_SKEW_LEEWAY_S,
            options={"require": ["sub"]},
        )
    except HTTPException:
        raise
    except Exception as e:  # imza/aud/expiry → 401 (detay loglanmaz)
        raise HTTPException(status_code=401, detail="Geçersiz veya süresi dolmuş oturum.") from e
    return AuthClaims(sub=payload["sub"], email=payload.get("email", ""))
