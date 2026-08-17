from fastapi.testclient import TestClient

from admin_api.main import app


def test_healthz_ok():
    with TestClient(app) as c:
        assert c.get("/admin/healthz").status_code == 200
        assert c.get("/admin/healthz").json() == {"status": "ok"}
