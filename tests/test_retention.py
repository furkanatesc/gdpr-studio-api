import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, event, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Invitation, Organization, User
from app.retention import purge_terminal_invitations


def _fk_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _rec):  # noqa: ANN001
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def _org_user(session):
    oid = uuid.uuid4()
    session.add(Organization(id=oid, name="Org"))
    u = User(supabase_user_id="sup", email="u@x.io")
    session.add(u)
    session.flush()
    return oid, u.id


def _invite(session, oid, uid, *, status, created_days_ago, expires_days):
    session.add(Invitation(
        org_id=oid, email="i@x.io", role="avukat", token=str(uuid.uuid4()),
        status=status,
        created_at=datetime.now(UTC) - timedelta(days=created_days_ago),
        expires_at=datetime.now(UTC) + timedelta(days=expires_days),
        invited_by=uid,
    ))


def test_purges_terminal_beyond_grace_keeps_live_and_recent():
    s = _fk_session()
    oid, uid = _org_user(s)
    _invite(s, oid, uid, status="accepted", created_days_ago=40, expires_days=-38)   # sil
    _invite(s, oid, uid, status="revoked", created_days_ago=40, expires_days=-38)    # sil
    _invite(s, oid, uid, status="pending", created_days_ago=40, expires_days=-38)    # sil (expired)
    _invite(s, oid, uid, status="pending", created_days_ago=40, expires_days=+5)     # KORU (canlı)
    _invite(s, oid, uid, status="accepted", created_days_ago=10, expires_days=-8)    # KORU (grace içi)
    s.commit()

    res = purge_terminal_invitations(s, retention_days=30)

    assert res["invitationsPurged"] == 3
    assert s.scalar(select(func.count()).select_from(Invitation)) == 2
