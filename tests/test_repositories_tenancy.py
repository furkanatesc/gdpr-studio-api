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


def test_revoke_happy_path():
    s = _session()
    accounts = AccountRepository(s)
    admin = accounts.create_user("sb-rev-1", "admin-rev@b.com")
    org = accounts.create_org_with_admin("Revoke Org", admin.id)
    s.flush()
    invs = InvitationRepository(s)
    exp = datetime.now(UTC) + timedelta(hours=72)
    inv = invs.create(org.id, "target@b.com", "avukat", "tok-rev-1", exp, admin.id)
    s.commit()

    result = invs.revoke(inv.id, org.id)
    s.commit()

    assert result is True
    assert inv.status == "revoked"
    assert invs.get_pending_by_email("target@b.com") is None


def test_revoke_cross_tenant_denied():
    s = _session()
    accounts = AccountRepository(s)
    admin1 = accounts.create_user("sb-ct-1", "admin-ct1@b.com")
    org1 = accounts.create_org_with_admin("Org One", admin1.id)
    admin2 = accounts.create_user("sb-ct-2", "admin-ct2@b.com")
    org2 = accounts.create_org_with_admin("Org Two", admin2.id)
    s.flush()
    invs = InvitationRepository(s)
    exp = datetime.now(UTC) + timedelta(hours=72)
    inv = invs.create(org1.id, "victim@b.com", "avukat", "tok-ct-1", exp, admin1.id)
    s.commit()

    result = invs.revoke(inv.id, org2.id)
    s.commit()

    assert result is False
    assert inv.status == "pending"
    assert invs.get_pending_by_email("victim@b.com") is not None


def test_revoke_already_revoked_returns_false():
    s = _session()
    accounts = AccountRepository(s)
    admin = accounts.create_user("sb-rr-1", "admin-rr@b.com")
    org = accounts.create_org_with_admin("Revoke Twice Org", admin.id)
    s.flush()
    invs = InvitationRepository(s)
    exp = datetime.now(UTC) + timedelta(hours=72)
    inv = invs.create(org.id, "once@b.com", "avukat", "tok-rr-1", exp, admin.id)
    s.commit()

    first = invs.revoke(inv.id, org.id)
    s.commit()
    second = invs.revoke(inv.id, org.id)
    s.commit()

    assert first is True
    assert second is False
    assert inv.status == "revoked"
