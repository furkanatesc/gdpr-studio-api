import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

import app.auth.jwt as jwtmod
import app.config as configmod
from app.auth.jwt import AuthClaims, reset_jwks_cache, verify_token
from app.config import Settings


@pytest.fixture()
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _make_token(key, *, aud="authenticated", sub="user-123", email="a@b.com"):
    return pyjwt.encode(
        {"sub": sub, "email": email, "aud": aud},
        key,
        algorithm="RS256",
        headers={"kid": "test-kid"},
    )


@pytest.fixture()
def _patch_signing_key(monkeypatch, rsa_key):
    # PyJWKClient yerine sabit public key döndür.
    class _Key:
        key = rsa_key.public_key()

    monkeypatch.setattr(jwtmod, "_signing_key_for", lambda token: _Key())
    reset_jwks_cache()
    yield
    reset_jwks_cache()


def test_valid_token_returns_claims(rsa_key, _patch_signing_key):
    token = _make_token(rsa_key)
    claims = verify_token(token)
    assert isinstance(claims, AuthClaims)
    assert claims.sub == "user-123"
    assert claims.email == "a@b.com"


def test_wrong_audience_rejected(rsa_key, _patch_signing_key):
    token = _make_token(rsa_key, aud="other")
    with pytest.raises(HTTPException) as exc:
        verify_token(token)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Geçersiz veya süresi dolmuş oturum."


def test_unconfigured_jwks_url_rejected():
    # _patch_signing_key fixture'ı kullanılmaz — gerçek _signing_key_for çalışır.
    saved = configmod._settings
    try:
        configmod._settings = Settings(_env_file=None, supabase_project_url="")
        reset_jwks_cache()
        with pytest.raises(HTTPException) as exc:
            verify_token("any.token.here")
        assert exc.value.status_code == 401
        assert exc.value.detail == "Kimlik doğrulama yapılandırılmamış."
    finally:
        configmod._settings = saved
        reset_jwks_cache()
