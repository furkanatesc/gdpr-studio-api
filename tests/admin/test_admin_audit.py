import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from admin_api.audit import recompute_row_hash, write_audit
from app.db import Base

_ADMIN = SimpleNamespace(admin_id=str(uuid.uuid4()), email="admin@example.com")


def _fresh_session():
    """A brand-new in-memory DB so the written row is first-in-chain (prev_hash is None)."""
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


@pytest.fixture()
def admin_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    yield sessionmaker(bind=engine, expire_on_commit=False)()


def test_chain_links_prev_hash(admin_db):
    a = write_audit(admin_db, actor=_ADMIN, action="x", reason="t1")
    b = write_audit(admin_db, actor=_ADMIN, action="y", reason="t2")
    assert b.prev_hash == a.row_hash


def test_row_hash_covers_fields(admin_db):
    a = write_audit(admin_db, actor=_ADMIN, action="x", reason="t1")
    assert a.row_hash and len(a.row_hash) == 64  # sha256 hex

    b = write_audit(admin_db, actor=_ADMIN, action="y", reason="t1")
    assert b.row_hash != a.row_hash  # different action -> different hash
    assert b.row_hash != b.prev_hash  # chained hash is not a no-op copy of prev

    c = write_audit(admin_db, actor=_ADMIN, action="y", reason="t2")
    assert c.row_hash != b.row_hash  # different reason -> different hash


def test_row_hash_covers_ip():
    # An owner with UPDATE could otherwise rewrite `ip` without breaking the chain.
    a = write_audit(_fresh_session(), actor=_ADMIN, action="x", reason="t", ip="1.1.1.1")
    b = write_audit(_fresh_session(), actor=_ADMIN, action="x", reason="t", ip="2.2.2.2")
    assert a.prev_hash is None and b.prev_hash is None  # both first-in-chain
    assert a.row_hash != b.row_hash


def test_row_hash_covers_request_id():
    a = write_audit(_fresh_session(), actor=_ADMIN, action="x", reason="t", request_id="r1")
    b = write_audit(_fresh_session(), actor=_ADMIN, action="x", reason="t", request_id="r2")
    assert a.row_hash != b.row_hash


def test_row_hash_covers_actor_email_snapshot():
    a1 = SimpleNamespace(admin_id=_ADMIN.admin_id, email="alice@example.com")
    a2 = SimpleNamespace(admin_id=_ADMIN.admin_id, email="mallory@example.com")
    a = write_audit(_fresh_session(), actor=a1, action="x", reason="t")
    b = write_audit(_fresh_session(), actor=a2, action="x", reason="t")
    assert a.row_hash != b.row_hash  # same admin_id, different snapshot email


def test_created_at_is_set_at_write_time():
    a = write_audit(_fresh_session(), actor=_ADMIN, action="x", reason="t")
    assert a.created_at is not None  # stamped in Python so it can be hashed


def test_recompute_detects_ip_tampering():
    row = write_audit(_fresh_session(), actor=_ADMIN, action="x", reason="t", ip="1.1.1.1")
    assert recompute_row_hash(row) == row.row_hash  # untampered verifies
    row.ip = "9.9.9.9"  # attacker rewrites origin
    assert recompute_row_hash(row) != row.row_hash


def test_recompute_detects_created_at_tampering():
    from datetime import timedelta

    row = write_audit(_fresh_session(), actor=_ADMIN, action="x", reason="t")
    assert recompute_row_hash(row) == row.row_hash
    row.created_at = row.created_at + timedelta(days=1)  # backdate/forward-date
    assert recompute_row_hash(row) != row.row_hash
