"""JWT issuer doğrulama (B2). RSA keypair üretilir, _signing_key_for patch'lenir."""
import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException

from app.auth import jwt as jwtmod


@pytest.fixture
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _make_token(rsa_key, *, iss: str | None, aud="authenticated"):
    payload = {"sub": "user-123", "email": "a@b.com", "aud": aud}
    if iss is not None:
        payload["iss"] = iss
    return pyjwt.encode(payload, rsa_key, algorithm="RS256")


def _patch(monkeypatch, rsa_key, issuer):
    class _FakeSettings:
        supabase_jwt_aud = "authenticated"
        supabase_issuer = issuer
        jwks_timeout_s = 10.0
    monkeypatch.setattr(jwtmod, "get_settings", lambda: _FakeSettings())

    class _Key:
        key = rsa_key.public_key()
    monkeypatch.setattr(jwtmod, "_signing_key_for", lambda token: _Key())


def test_correct_issuer_passes(monkeypatch, rsa_key):
    _patch(monkeypatch, rsa_key, "https://proj.supabase.co/auth/v1")
    token = _make_token(rsa_key, iss="https://proj.supabase.co/auth/v1")
    claims = jwtmod.verify_token(token)
    assert claims.sub == "user-123"


def test_wrong_issuer_rejected(monkeypatch, rsa_key):
    _patch(monkeypatch, rsa_key, "https://proj.supabase.co/auth/v1")
    token = _make_token(rsa_key, iss="https://evil.example/auth/v1")
    with pytest.raises(HTTPException) as ei:
        jwtmod.verify_token(token)
    assert ei.value.status_code == 401


def test_missing_issuer_rejected_when_configured(monkeypatch, rsa_key):
    _patch(monkeypatch, rsa_key, "https://proj.supabase.co/auth/v1")
    token = _make_token(rsa_key, iss=None)
    with pytest.raises(HTTPException) as ei:
        jwtmod.verify_token(token)
    assert ei.value.status_code == 401
