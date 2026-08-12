"""İmzalı/expire davet token'ı (itsdangerous). Token uygulamada üretilir."""

from __future__ import annotations

import hashlib

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..config import get_settings

_SALT = "invite-v1"


class InviteInvalid(Exception):
    pass


class InviteExpired(Exception):
    pass


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().invite_secret, salt=_SALT)


def make_invite_token(org_id: str, email: str) -> str:
    return _serializer().dumps({"org_id": org_id, "email": email})


def hash_invite_token(token: str) -> str:
    """Yüksek-entropili (imzalı) token için deterministik SHA-256 hex — DB lookup içindir."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def read_invite_token(token: str, max_age_s: int | None = None) -> dict:
    if max_age_s is None:
        max_age_s = get_settings().invite_ttl_hours * 3600
    try:
        return _serializer().loads(token, max_age=max_age_s)
    except SignatureExpired as e:
        raise InviteExpired() from e
    except BadSignature as e:
        raise InviteInvalid() from e
