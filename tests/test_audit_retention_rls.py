"""audit purge kvkk_app ile REVOKE nedeniyle SİLEMEZ → owner gerekir (H3-3).
test_audit_rls.py deseni; RLS_TEST_DATABASE_URL yoksa skip."""
import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.retention import purge_audit_logs

DB_URL = os.getenv("RLS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="Gerçek-PG gerekli (RLS_TEST_DATABASE_URL)")


def test_kvkk_app_cannot_purge_audit_logs():
    eng = create_engine(DB_URL, future=True)
    org = uuid.uuid4()
    with eng.connect() as conn:
        trans = conn.begin()
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        conn.execute(text("INSERT INTO organizations (id, name) VALUES (:i, 'O')"), {"i": str(org)})
        conn.execute(
            text("INSERT INTO audit_logs (id, org_id, action, created_at) "
                 "VALUES (:i, :o, 'x', :t)"),
            {"i": str(uuid.uuid4()), "o": str(org),
             "t": datetime.now(UTC) - timedelta(days=800)},
        )
        trans.commit()
    try:
        with Session(bind=eng) as s, pytest.raises(Exception):  # noqa: B017
            purge_audit_logs(s, retention_days=730)
    finally:
        with eng.connect() as conn:
            conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
            conn.execute(text("DELETE FROM organizations WHERE id = :i"), {"i": str(org)})
            conn.commit()
        eng.dispose()
