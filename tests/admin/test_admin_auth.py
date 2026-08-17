import pytest
from fastapi import HTTPException

from admin_api import auth


class _Claims(dict):
    pass


def test_tenant_audience_rejected(monkeypatch):
    monkeypatch.setattr(auth, "_verify", lambda tok: {"sub": "u1", "aud": "authenticated", "aal": "aal2"})
    with pytest.raises(HTTPException) as e:
        auth._identity_from_claims(auth._verify("x"), session=None)
    assert e.value.status_code == 401


def test_aal1_rejected(monkeypatch):
    with pytest.raises(HTTPException) as e:
        auth._require_aal2({"sub": "u1", "aud": "platform-admin", "aal": "aal1"})
    assert e.value.status_code == 403


def test_missing_aal_rejected():
    with pytest.raises(HTTPException) as e:
        auth._require_aal2({"sub": "u1", "aud": "platform-admin"})
    assert e.value.status_code == 403
