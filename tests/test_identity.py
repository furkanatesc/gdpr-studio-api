import types
import uuid

import pytest
from fastapi import HTTPException

import app.config as config_module
from app.auth.identity import Identity, _claims_from_request, require_role


def test_require_role_blocks_wrong_role():
    ident = Identity(user_id=uuid.uuid4(), org_id=uuid.uuid4(), role="avukat", email="a@b.com")
    dep = require_role("yonetici")
    with pytest.raises(HTTPException) as exc:
        dep(ident)
    assert exc.value.status_code == 403


def test_require_role_allows_match():
    ident = Identity(user_id=uuid.uuid4(), org_id=uuid.uuid4(), role="yonetici", email="a@b.com")
    assert require_role("yonetici")(ident) is ident


def test_claims_production_dev_bypass_raises_401():
    """Production ortamında dev-bypass aktifken 401 fırlatılmalı."""
    prev = config_module._settings
    try:
        config_module._settings = config_module.Settings(
            _env_file=None,
            environment="production",
            auth_dev_bypass=True,
            supabase_project_url="",
        )
        stub = types.SimpleNamespace(headers={})
        with pytest.raises(HTTPException) as exc:
            _claims_from_request(stub)
        assert exc.value.status_code == 401
    finally:
        config_module._settings = prev


def test_claims_non_production_dev_bypass_returns_dev_claims():
    """Production dışında dev-bypass aktifken dev kimliği döndürülmeli."""
    prev = config_module._settings
    try:
        config_module._settings = config_module.Settings(
            _env_file=None,
            environment="development",
            auth_dev_bypass=True,
            supabase_project_url="",
        )
        stub = types.SimpleNamespace(headers={})
        from app.auth.identity import _DEV_SUB

        claims = _claims_from_request(stub)
        assert claims.sub == _DEV_SUB
    finally:
        config_module._settings = prev
