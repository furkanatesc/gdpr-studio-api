import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from admin_api.audit import write_audit
from app.db import Base

_ADMIN = SimpleNamespace(admin_id=str(uuid.uuid4()), email="admin@example.com")


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
