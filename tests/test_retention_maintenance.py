import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import AuditLog, Organization
from app.retention_maintenance import run_audit_retention


def _engine():
    eng = create_engine("sqlite+pysqlite:///:memory:",
                        connect_args={"check_same_thread": False},
                        poolclass=StaticPool, future=True)

    @event.listens_for(eng, "connect")
    def _fk(dbapi_conn, _r):  # noqa: ANN001
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    return eng


def test_run_deletes_old_audit(monkeypatch):
    from app import config
    config.get_settings().audit_retention_days = 730
    eng = _engine()
    Session = sessionmaker(bind=eng)
    with Session() as s:
        oid = uuid.uuid4()
        s.add(Organization(id=oid, name="O"))
        s.flush()
        s.add(AuditLog(org_id=oid, action="old",
                       created_at=datetime.now(UTC) - timedelta(days=800)))
        s.commit()

    run_audit_retention(engine=eng)

    with Session() as s:
        assert s.scalar(select(func.count()).select_from(AuditLog)) == 0


def test_run_swallows_errors(monkeypatch):
    import app.retention_maintenance as rm

    def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(rm, "purge_audit_logs", boom)
    run_audit_retention(engine=_engine())  # exception fırlatmamalı
