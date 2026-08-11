"""Owner-rol bakım süreci (H3-3): audit retention purge. start.sh'te uvicorn'dan ÖNCE
koşar (MIGRATION_DATABASE_URL = owner; app engine DEĞİL — o kvkk_app + RLS-guard).
Hataları yutar → deploy/serve'i bloke etmez."""

from __future__ import annotations

import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .config import get_settings, normalize_pg_url
from .retention import purge_audit_logs

_log = logging.getLogger("app.retention")


def _owner_engine():
    url = normalize_pg_url(os.getenv("MIGRATION_DATABASE_URL") or get_settings().database_url)
    return create_engine(url, future=True)


def run_audit_retention(engine=None) -> None:
    try:
        eng = engine or _owner_engine()
        with Session(bind=eng) as session:
            purge_audit_logs(session, retention_days=get_settings().audit_retention_days)
    except Exception:
        _log.exception("audit retention bakımı başarısız (deploy bloke edilmez)")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_audit_retention()
