import pytest
from fastapi.testclient import TestClient

from admin_api import main
from admin_api.config import AdminSettings
from admin_api.main import app


def test_healthz_ok():
    with TestClient(app) as c:
        assert c.get("/admin/healthz").status_code == 200
        assert c.get("/admin/healthz").json() == {"status": "ok"}


def test_prod_requires_admin_redis_url(monkeypatch):
    # In production an empty ADMIN_REDIS_URL silently disables the rate-limiter → self-DoS
    # exposure. Boot must fail-closed instead.
    monkeypatch.setattr(main, "verify_admin_role_and_head", lambda *a, **k: None)
    s = AdminSettings(environment="production", admin_redis_url="", admin_database_url="sqlite://")
    monkeypatch.setattr(main, "get_admin_settings", lambda: s)
    with pytest.raises(RuntimeError, match="ADMIN_REDIS_URL"):
        with TestClient(main.app):
            pass


def test_prod_with_redis_url_boots(monkeypatch):
    monkeypatch.setattr(main, "verify_admin_role_and_head", lambda *a, **k: None)
    monkeypatch.setattr(main, "get_admin_engine", lambda: None)
    s = AdminSettings(
        environment="production",
        admin_redis_url="redis://localhost:6379/0",
        admin_bff_secret="test-secret",
        admin_database_url="sqlite://",
    )
    monkeypatch.setattr(main, "get_admin_settings", lambda: s)
    with TestClient(main.app) as c:  # no raise
        assert c.get("/admin/healthz").status_code == 200


def test_dev_allows_empty_redis(monkeypatch):
    s = AdminSettings(environment="development", admin_redis_url="")
    monkeypatch.setattr(main, "get_admin_settings", lambda: s)
    with TestClient(main.app) as c:  # dev never boot-guards redis
        assert c.get("/admin/healthz").status_code == 200


def test_prod_requires_admin_bff_secret(monkeypatch):
    monkeypatch.setattr(main, "verify_admin_role_and_head", lambda *a, **k: None)
    monkeypatch.setattr(main, "get_admin_engine", lambda: None)
    s = AdminSettings(
        environment="production",
        admin_redis_url="redis://x:6379/0",
        admin_bff_secret="",
        admin_database_url="sqlite://",
    )
    monkeypatch.setattr(main, "get_admin_settings", lambda: s)
    with pytest.raises(RuntimeError, match="ADMIN_BFF_SECRET"):
        with TestClient(main.app):
            pass
