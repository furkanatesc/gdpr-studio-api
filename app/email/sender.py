"""Pluggable e-posta: dev=log (sağlayıcısız), prod=Resend (EU). Env-gated."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from ..config import get_settings

_log = logging.getLogger("app.email")


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    html: str


class EmailSender(Protocol):
    def send(self, msg: EmailMessage) -> None: ...


class LogEmailSender:
    """Geliştirme: e-postayı göndermeden loglar (gövde loglanmaz, yalnız meta)."""

    def send(self, msg: EmailMessage) -> None:
        _log.info("E-posta (log) → %s | konu: %s", msg.to, msg.subject)


class ResendEmailSender:
    def __init__(self, api_key: str, sender: str) -> None:
        self._api_key = api_key
        self._from = sender

    def send(self, msg: EmailMessage) -> None:
        try:
            resp = httpx.post(
                "https://api.resend.com/emails",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"from": self._from, "to": [msg.to], "subject": msg.subject, "html": msg.html},
                timeout=10.0,
            )
            resp.raise_for_status()
        except Exception as e:  # teslim hatası üretimi durdurmaz
            _log.warning("E-posta gönderilemedi (%s): %s", msg.to, e)


_sender: EmailSender | None = None


def reset_email_sender() -> None:
    global _sender
    _sender = None


def get_email_sender() -> EmailSender:
    global _sender
    if _sender is not None:
        return _sender
    s = get_settings()
    if s.email_provider == "resend" and s.resend_api_key:
        _sender = ResendEmailSender(s.resend_api_key, s.email_from)
    else:
        _sender = LogEmailSender()
    return _sender
