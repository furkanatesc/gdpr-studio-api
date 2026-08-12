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
        org_id=oid, email="i@x.io", role="avukat", token_hash=str(uuid.uuid4()),
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


def test_retention_sweep_purges_invitations_and_orgs():
    from app.models import Membership
    from app.retention import retention_sweep

    s = _fk_session()
    # süresi dolmuş silinecek org
    dead = uuid.uuid4()
    s.add(Organization(id=dead, name="Dead", status="deleting",
                       deleted_at=datetime.now(UTC) - timedelta(days=20)))
    du = User(supabase_user_id="d", email="d@x.io")
    s.add(du)
    s.flush()
    s.add(Membership(user_id=du.id, org_id=dead, role="yonetici"))
    # ayrı canlı org + eski terminal davet
    live, uid = _org_user(s)
    _invite(s, live, uid, status="accepted", created_days_ago=40, expires_days=-38)
    s.commit()

    res = retention_sweep(s, invite_retention_days=30, org_grace_days=14)

    assert res["invitationsPurged"] == 1
    assert res["orgsPurged"] == 1
    assert s.get(Organization, dead) is None
    assert s.get(Organization, live) is not None


def test_purge_audit_logs_deletes_old_keeps_recent_and_noop_on_zero():
    from app.models import AuditLog
    from app.retention import purge_audit_logs

    s = _fk_session()
    oid, _ = _org_user(s)
    s.add(AuditLog(org_id=oid, action="old",
                   created_at=datetime.now(UTC) - timedelta(days=800)))
    s.add(AuditLog(org_id=oid, action="new",
                   created_at=datetime.now(UTC) - timedelta(days=10)))
    s.commit()

    assert purge_audit_logs(s, retention_days=0)["auditLogsPurged"] == 0
    res = purge_audit_logs(s, retention_days=730)
    assert res["auditLogsPurged"] == 1
    remaining = [a.action for a in s.scalars(select(AuditLog))]
    assert remaining == ["new"]


def test_startup_sweep_via_flag(monkeypatch):
    """dsar_purge_on_startup açıkken lifespan retention_sweep çağırır (davet dahil)."""
    from app import main
    called = {}
    monkeypatch.setattr(main, "get_engine", lambda: None)
    monkeypatch.setattr(
        "app.retention.retention_sweep",
        lambda *a, **k: called.setdefault("hit", True) or {"invitationsPurged": 0, "orgsPurged": 0, "purged": []},
    )
    main.settings.dsar_purge_on_startup = True
    main._run_startup_purge()  # exception fırlatmamalı

    assert called.get("hit") is True   # sweep GERÇEKTEN çağrıldı (yol doğrulandı)
