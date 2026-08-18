from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from admin_api.auth import PlatformAdminIdentity, require_platform_admin
from admin_api.db import admin_session
from admin_api.main import app
from app.db import Base
from app.models import PlatformMetricDaily

_IDENTITY = PlatformAdminIdentity(
    "11111111-1111-1111-1111-111111111111", "sub", "a@b.co", "sub"
)


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()

    today = date.today()
    session.add_all(
        [
            PlatformMetricDaily(
                day=today - timedelta(days=1),
                metric_key="tenants_active",
                dims={},
                value_numeric=10,
            ),
            PlatformMetricDaily(
                day=today,
                metric_key="tenants_active",
                dims={},
                value_numeric=12,
            ),
            PlatformMetricDaily(
                day=today,
                metric_key="subs_active",
                dims={"plan": "pro"},
                value_numeric=5,
            ),
        ]
    )
    session.commit()

    def _override_session():
        yield session

    app.dependency_overrides[require_platform_admin] = lambda: _IDENTITY
    app.dependency_overrides[admin_session] = _override_session

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()
    session.close()


def test_timeseries_reads_rollup(client):
    resp = client.get("/admin/metrics/timeseries", params={"metric": "tenants_active", "range": 30})
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["points"], list)
    assert len(body["points"]) == 2


def test_timeseries_range_cap(client):
    resp = client.get("/admin/metrics/timeseries", params={"metric": "x", "range": 9999})
    assert resp.status_code == 422


def test_overview_returns_latest(client):
    resp = client.get("/admin/metrics/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body["metrics"], dict)
    assert body["metrics"]["tenants_active"] == 12
