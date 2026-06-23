import logging

import app.config as config_module
from app.email.sender import EmailMessage, get_email_sender, reset_email_sender


def test_log_sender_used_by_default(caplog):
    config_module._settings = config_module.Settings(_env_file=None, email_provider="log")
    reset_email_sender()
    with caplog.at_level(logging.INFO, logger="app.email"):
        get_email_sender().send(EmailMessage(to="a@b.com", subject="Davet", html="<p>hi</p>"))
    assert any("a@b.com" in r.message for r in caplog.records)
    config_module._settings = None
    reset_email_sender()
