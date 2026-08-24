import time
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from admin_api import auth
from app.db import Base
from app.models import PlatformAdmin

_NOW = 1_000_000_000.0


def _session_with(admin=None):
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine, expire_on_commit=False)()
    if admin is not None:
        s.add(admin)
        s.commit()
    return s


def _req(authorization=None):
    headers = {} if authorization is None else {"authorization": authorization}
    return SimpleNamespace(headers=headers)


def _valid_claims(sub):
    return {"sub": sub, "aud": "platform-admin", "aal": "aal2", "amr": [_totp(time.time())]}


def _totp(ts):
    return {"method": "totp", "timestamp": ts}


def _password(ts):
    return {"method": "password", "timestamp": ts}


def test_tenant_audience_rejected(monkeypatch):
    monkeypatch.setattr(auth, "_verify", lambda tok: {"sub": "u1", "aud": "authenticated", "aal": "aal2"})
    with pytest.raises(HTTPException) as e:
        auth._identity_from_claims(auth._verify("x"), session=None)
    assert e.value.status_code == 401


def test_aal1_rejected():
    with pytest.raises(HTTPException) as e:
        auth._require_mfa({"aal": "aal1", "amr": [_totp(_NOW)]}, now=_NOW)
    assert e.value.status_code == 401  # spec §4.2 fail-closed


def test_missing_aal_rejected():
    with pytest.raises(HTTPException) as e:
        auth._require_mfa({"amr": [_totp(_NOW)]}, now=_NOW)
    assert e.value.status_code == 401


def test_aal2_but_amr_missing_rejected():
    with pytest.raises(HTTPException) as e:
        auth._require_mfa({"aal": "aal2"}, now=_NOW)
    assert e.value.status_code == 401


def test_aal2_amr_password_only_rejected():
    # aal2 stamped but the only auth factor is a password → no recent MFA factor
    with pytest.raises(HTTPException) as e:
        auth._require_mfa({"aal": "aal2", "amr": [_password(_NOW)]}, now=_NOW)
    assert e.value.status_code == 401


def test_aal2_recent_totp_accepted():
    # aal2 + a recent MFA factor alongside the password → passes (no raise)
    auth._require_mfa({"aal": "aal2", "amr": [_password(_NOW), _totp(_NOW)]}, now=_NOW)


def test_aal2_stale_mfa_rejected():
    # MFA factor present but far in the past → not "recent" → fail-closed
    with pytest.raises(HTTPException) as e:
        auth._require_mfa({"aal": "aal2", "amr": [_totp(_NOW - 100_000)]}, now=_NOW)
    assert e.value.status_code == 401


def test_mfa_prefixed_method_accepted():
    # GoTrue may prefix the factor as "mfa/totp"
    auth._require_mfa({"aal": "aal2", "amr": [{"method": "mfa/totp", "timestamp": _NOW}]}, now=_NOW)


# --- require_platform_admin (end-to-end dependency) ---


def test_missing_bearer_returns_401():
    with pytest.raises(HTTPException) as e:
        auth.require_platform_admin(_req(None), session=None)
    assert e.value.status_code == 401 and e.value.detail == "missing_token"


def test_malformed_bearer_returns_401():
    with pytest.raises(HTTPException) as e:
        auth.require_platform_admin(_req("Token abc"), session=None)
    assert e.value.status_code == 401 and e.value.detail == "missing_token"


def test_verify_failure_returns_401(monkeypatch):
    # fail-closed except: any decode/JWKS error collapses to 401, details not leaked
    def _boom(_tok):
        raise ValueError("jwks unreachable")

    monkeypatch.setattr(auth, "_verify", _boom)
    with pytest.raises(HTTPException) as e:
        auth.require_platform_admin(_req("Bearer x"), session=_session_with())
    assert e.value.status_code == 401 and e.value.detail == "invalid_token"


def test_active_admin_passes(monkeypatch):
    admin = PlatformAdmin(supabase_user_id="s1", email="a@example.com", is_active=True)
    session = _session_with(admin)
    monkeypatch.setattr(auth, "_verify", lambda _tok: _valid_claims("s1"))
    identity = auth.require_platform_admin(_req("Bearer x"), session=session)
    assert identity.supabase_user_id == "s1" and identity.email == "a@example.com"


def test_inactive_admin_returns_403(monkeypatch):
    # the row EXISTS but is deactivated → only the live is_active filter separates 403 from success
    admin = PlatformAdmin(supabase_user_id="s2", email="b@example.com", is_active=False)
    session = _session_with(admin)
    monkeypatch.setattr(auth, "_verify", lambda _tok: _valid_claims("s2"))
    with pytest.raises(HTTPException) as e:
        auth.require_platform_admin(_req("Bearer x"), session=session)
    assert e.value.status_code == 403 and e.value.detail == "not_platform_admin"
