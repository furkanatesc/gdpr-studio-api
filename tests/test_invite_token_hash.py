"""Davet token hash'leme (B5)."""
from app.invites.tokens import hash_invite_token


def test_hash_is_deterministic_sha256_hex():
    h1 = hash_invite_token("abc.def.ghi")
    h2 = hash_invite_token("abc.def.ghi")
    assert h1 == h2
    assert len(h1) == 64
    assert h1 != "abc.def.ghi"


def test_different_tokens_differ():
    assert hash_invite_token("a") != hash_invite_token("b")


def test_invite_out_has_no_token_field():
    from app.modules.invitations import InviteOut
    assert "token" not in InviteOut.model_fields
