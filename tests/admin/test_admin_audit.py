import itertools
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from admin_api.audit import write_audit
from app.db import Base
from app.models import PlatformAuditLog

_ADMIN = SimpleNamespace(admin_id=str(uuid.uuid4()), email="admin@example.com")


@pytest.fixture()
def admin_db():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)

    # sqlite only aliases an INTEGER (not BIGINT) primary key to its internal
    # rowid autoincrement; PlatformAuditLog.id is BigInteger, so on sqlite it
    # needs an explicit value. Assign one here — Postgres keeps using its own
    # sequence in production, this is a sqlite-test-only shim.
    counter = itertools.count(1)

    def _assign_id(mapper, connection, target):
        if target.id is None:
            target.id = next(counter)

    event.listen(PlatformAuditLog, "before_insert", _assign_id)
    try:
        yield sessionmaker(bind=engine, expire_on_commit=False)()
    finally:
        event.remove(PlatformAuditLog, "before_insert", _assign_id)


def test_chain_links_prev_hash(admin_db):
    a = write_audit(admin_db, actor=_ADMIN, action="x", reason="t1")
    b = write_audit(admin_db, actor=_ADMIN, action="y", reason="t2")
    assert b.prev_hash == a.row_hash


def test_row_hash_covers_fields(admin_db):
    a = write_audit(admin_db, actor=_ADMIN, action="x", reason="t1")
    assert a.row_hash and len(a.row_hash) == 64  # sha256 hex
