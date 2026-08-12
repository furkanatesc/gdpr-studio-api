"""invite_secret prod startup guard (B3) — saf predikat tablo testi."""
import pytest

from app.auth.startup_guard import invite_secret_violation, verify_invite_secret

_DEFAULT = "dev-invite-secret-change-me"


@pytest.mark.parametrize(
    "env,secret,expect_reason",
    [
        ("production", "", True),
        ("production", _DEFAULT, True),
        ("production", "a-strong-random-secret-value", False),
        ("development", "", False),
        ("development", _DEFAULT, False),
    ],
)
def test_invite_secret_violation(env, secret, expect_reason):
    reason = invite_secret_violation(env, secret)
    assert (reason is not None) == expect_reason


def test_verify_raises_in_prod_with_default():
    class _S:
        environment = "production"
        invite_secret = _DEFAULT
    with pytest.raises(RuntimeError):
        verify_invite_secret(_S())


def test_verify_noop_in_dev():
    class _S:
        environment = "development"
        invite_secret = _DEFAULT
    verify_invite_secret(_S())  # raise etmemeli
