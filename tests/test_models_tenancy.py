import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Invitation, Membership, Organization, User


def _session():
    eng = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng, expire_on_commit=False)()


def test_org_user_membership_roundtrip():
    s = _session()
    org = Organization(name="Acme Hukuk")
    user = User(supabase_user_id="sb-1", email="a@b.com")
    s.add_all([org, user])
    s.flush()
    m = Membership(user_id=user.id, org_id=org.id, role="yonetici")
    s.add(m)
    s.commit()
    assert isinstance(org.id, uuid.UUID)
    assert s.query(Membership).filter_by(org_id=org.id).one().role == "yonetici"


def test_invitation_defaults_pending():
    s = _session()
    org = Organization(name="Acme")
    s.add(org)
    s.flush()
    inv = Invitation(org_id=org.id, email="x@y.com", role="avukat", token="tok-1")
    s.add(inv)
    s.commit()
    assert inv.status == "pending"
