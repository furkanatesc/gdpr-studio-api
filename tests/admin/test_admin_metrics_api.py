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
def session_factory():
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
        ]
    )
    session.commit()

    yield session

    session.close()


@pytest.fixture()
def client(session_factory):
    session = session_factory

    def _override_session():
        yield session

    app.dependency_overrides[require_platform_admin] = lambda: _IDENTITY
    app.dependency_overrides[admin_session] = _override_session

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


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
    metrics = body["metrics"]
    assert isinstance(metrics, list)
    tenants_rows = [row for row in metrics if row["metricKey"] == "tenants_active"]
    assert len(tenants_rows) == 1
    assert tenants_rows[0]["value"] == 12
    assert tenants_rows[0]["dims"] == {}


def test_overview_preserves_dims(client, session_factory):
    session = session_factory
    today = date.today()
    session.add_all(
        [
            PlatformMetricDaily(
                day=today,
                metric_key="subs_active",
                dims={"plan": "pro"},
                value_numeric=3,
            ),
            PlatformMetricDaily(
                day=today,
                metric_key="subs_active",
                dims={"plan": "free"},
                value_numeric=10,
            ),
        ]
    )
    session.commit()

    resp = client.get("/admin/metrics/overview")
    assert resp.status_code == 200
    body = resp.json()
    metrics = body["metrics"]
    assert isinstance(metrics, list)

    subs_rows = [row for row in metrics if row["metricKey"] == "subs_active"]
    assert len(subs_rows) == 2
    by_plan = {row["dims"]["plan"]: row["value"] for row in subs_rows}
    assert by_plan == {"pro": 3, "free": 10}

    tenants_rows = [row for row in metrics if row["metricKey"] == "tenants_active"]
    assert len(tenants_rows) == 1
    assert tenants_rows[0]["value"] == 12
    assert tenants_rows[0]["dims"] == {}


def test_timeseries_preserves_dims(client, session_factory):
    session = session_factory
    today = date.today()
    session.add_all(
        [
            PlatformMetricDaily(
                day=today,
                metric_key="subs_active",
                dims={"plan": "pro"},
                value_numeric=3,
            ),
            PlatformMetricDaily(
                day=today,
                metric_key="subs_active",
                dims={"plan": "free"},
                value_numeric=10,
            ),
        ]
    )
    session.commit()

    resp = client.get(
        "/admin/metrics/timeseries", params={"metric": "subs_active", "range": 30}
    )
    assert resp.status_code == 200
    body = resp.json()
    points = body["points"]
    plans = {point["dims"]["plan"] for point in points}
    assert plans == {"pro", "free"}
    values_by_plan = {point["dims"]["plan"]: point["value"] for point in points}
    assert values_by_plan == {"pro": 3, "free": 10}
