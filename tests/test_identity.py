import uuid

import pytest
from fastapi import HTTPException

from app.auth.identity import Identity, require_role


def test_require_role_blocks_wrong_role():
    ident = Identity(user_id=uuid.uuid4(), org_id=uuid.uuid4(), role="avukat", email="a@b.com")
    dep = require_role("yonetici")
    with pytest.raises(HTTPException) as exc:
        dep(ident)
    assert exc.value.status_code == 403


def test_require_role_allows_match():
    ident = Identity(user_id=uuid.uuid4(), org_id=uuid.uuid4(), role="yonetici", email="a@b.com")
    assert require_role("yonetici")(ident) is ident
