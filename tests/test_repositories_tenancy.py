from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.repositories import AccountRepository, InvitationRepository


def _session():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, expire_on_commit=False)()


def test_create_user_and_org_with_admin():
    s = _session()
    accounts = AccountRepository(s)
    user = accounts.create_user("sb-1", "a@b.com")
    org = accounts.create_org_with_admin("Acme Hukuk", user.id)
    s.commit()
    m = accounts.get_membership_for_user(user.id)
    assert m.org_id == org.id and m.role == "yonetici"


def test_invitation_lifecycle():
    s = _session()
    accounts = AccountRepository(s)
    admin = accounts.create_user("sb-1", "admin@b.com")
    org = accounts.create_org_with_admin("Acme", admin.id)
    s.flush()
    invs = InvitationRepository(s)
    exp = datetime.now(UTC) + timedelta(hours=72)
    inv = invs.create(org.id, "x@y.com", "avukat", "tok-1", exp, admin.id)
    s.commit()
    assert invs.get_by_token("tok-1").id == inv.id
    assert invs.get_pending_by_email("x@y.com").id == inv.id
    invs.mark_accepted(inv)
    s.commit()
    assert invs.get_pending_by_email("x@y.com") is None
