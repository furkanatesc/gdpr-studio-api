import pytest

from app.invites.tokens import (
    InviteExpired,
    InviteInvalid,
    make_invite_token,
    read_invite_token,
)


def test_roundtrip():
    tok = make_invite_token("org-1", "a@b.com")
    data = read_invite_token(tok)
    assert data == {"org_id": "org-1", "email": "a@b.com"}


def test_expired():
    tok = make_invite_token("org-1", "a@b.com")
    with pytest.raises(InviteExpired):
        read_invite_token(tok, max_age_s=-1)


def test_tampered():
    with pytest.raises(InviteInvalid):
        read_invite_token("garbage.token.value")
