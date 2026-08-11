import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base
from app.models import Organization


def _session():
    eng = create_engine("sqlite+pysqlite:///:memory:",
                        connect_args={"check_same_thread": False},
                        poolclass=StaticPool, future=True)
    eng.dialect.supports_native_boolean = True
    from sqlalchemy import event

    @event.listens_for(eng, "connect")
    def _fk(c, _r):  # noqa: ANN001
        c.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    return sessionmaker(bind=eng)()


def test_suspended_status_allowed():
    s = _session()
    s.add(Organization(id=uuid.uuid4(), name="O", status="suspended"))
    s.commit()


def test_invalid_status_rejected():
    s = _session()
    s.add(Organization(id=uuid.uuid4(), name="O", status="bogus"))
    with pytest.raises(IntegrityError):
        s.commit()
