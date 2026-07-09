"""Compliance uçları — checklist + status upsert + rol + org kapsamı."""

import contextlib
import uuid

from fastapi.testclient import TestClient

import app.config as config_module
from app.auth.identity import Identity, get_current_identity
from app.db import get_session
from app.main import app
from app.models import ComplianceRequirement, GeneratedDocument
from app.redis_client import reset_redis

_ORG = uuid.UUID("00000000-0000-0000-0000-000000000002")  # _DEV_IDENTITY org
_ORG_B = uuid.UUID("00000000-0000-0000-0000-0000000000bb")
_USER_B = uuid.UUID("00000000-0000-0000-0000-0000000000cc")


def _seed_two_requirements(db_session):
    db_session.add_all([
        ComplianceRequirement(
            key="aydinlatma_x", title="Aydınlatma", madde_ref="KVKK m.10",
            description="d1", group="Belgelendirme", source_type="auto",
            auto_signal="doc_generated:aydinlatma", sort_order=1,
        ),
        ComplianceRequirement(
            key="manual_y", title="Politika", madde_ref="KVKK m.12",
            description="d2", group="Teknik/İdari", source_type="manual",
            auto_signal=None, sort_order=2,
        ),
    ])
    db_session.commit()


def _as_identity(role="yonetici", org_id=_ORG, user_id=_ORG):
    return lambda: Identity(user_id=user_id, org_id=org_id, role=role, email="x@y.io")


# --- checklist ---

def test_checklist_empty_when_no_requirements(client):
    r = client.get("/api/compliance/checklist")
    assert r.status_code == 200
    body = r.json()
    assert body["groups"] == []
    assert body["score"] is None
    assert body["groupScores"] == {}


def test_auto_item_suggestion_eksik_when_no_doc(client, db_session):
    _seed_two_requirements(db_session)
    r = client.get("/api/compliance/checklist")
    assert r.status_code == 200
    items = {i["key"]: i for g in r.json()["groups"] for i in g["items"]}
    assert items["aydinlatma_x"]["status"] is None
    assert items["aydinlatma_x"]["suggestion"] == "eksik"  # auto, saklı status yok, belge yok
    assert items["manual_y"]["suggestion"] is None  # manual → öneri yok
    # camelCase alias doğrula
    assert items["aydinlatma_x"]["maddeRef"] == "KVKK m.10"
    assert items["aydinlatma_x"]["sourceType"] == "auto"


def test_auto_item_suggestion_yapildi_when_doc_generated(client, db_session):
    _seed_two_requirements(db_session)
    db_session.add(GeneratedDocument(org_id=_ORG, doc_type="aydinlatma"))
    db_session.commit()
    r = client.get("/api/compliance/checklist")
    items = {i["key"]: i for g in r.json()["groups"] for i in g["items"]}
    assert items["aydinlatma_x"]["suggestion"] == "yapildi"


def test_put_status_updates_and_score(client, db_session):
    _seed_two_requirements(db_session)
    r = client.put("/api/compliance/status/aydinlatma_x", json={"status": "yapildi", "note": "kanit"})
    assert r.status_code == 200
    assert r.json()["status"] == "yapildi"
    assert r.json()["note"] == "kanit"
    assert r.json()["suggestion"] is None  # status saklandı → öneri gizli

    r2 = client.get("/api/compliance/checklist")
    body = r2.json()
    assert body["score"] == 0.5  # 1 yapildi / (2 - 0 uygulanmaz)
    assert body["groupScores"]["Belgelendirme"] == 1.0
    assert body["groupScores"]["Teknik/İdari"] == 0.0


def test_uygulanmaz_excluded_from_denominator(client, db_session):
    _seed_two_requirements(db_session)
    client.put("/api/compliance/status/aydinlatma_x", json={"status": "yapildi"})
    client.put("/api/compliance/status/manual_y", json={"status": "uygulanmaz"})
    body = client.get("/api/compliance/checklist").json()
    assert body["score"] == 1.0  # 1 / (2 - 1)


def test_groups_structure_and_order(client, db_session):
    _seed_two_requirements(db_session)
    groups = client.get("/api/compliance/checklist").json()["groups"]
    assert [g["group"] for g in groups] == ["Belgelendirme", "Teknik/İdari"]  # sort_order
    assert len(groups[0]["items"]) == 1 and len(groups[1]["items"]) == 1


# --- roller ---

def test_avukat_can_put_status(client, db_session):
    _seed_two_requirements(db_session)
    app.dependency_overrides[get_current_identity] = _as_identity(role="avukat")
    try:
        r = client.put("/api/compliance/status/aydinlatma_x", json={"status": "eksik"})
        assert r.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_identity, None)


def test_invalid_key_404(client, db_session):
    _seed_two_requirements(db_session)
    r = client.put("/api/compliance/status/yok_boyle", json={"status": "yapildi"})
    assert r.status_code == 404


def test_invalid_status_422(client, db_session):
    _seed_two_requirements(db_session)
    r = client.put("/api/compliance/status/aydinlatma_x", json={"status": "bogus"})
    assert r.status_code == 422


def test_extra_field_rejected_422(client, db_session):
    _seed_two_requirements(db_session)
    r = client.put("/api/compliance/status/aydinlatma_x", json={"status": "yapildi", "junk": 1})
    assert r.status_code == 422


# --- org kapsamı (SQLite WHERE-filtresiyle izolasyon; DB-RLS testi ayrı, Postgres-gated) ---

def test_checklist_is_org_scoped(client, db_session):
    _seed_two_requirements(db_session)
    # org A (dev kimliği) yapildi yazar
    client.put("/api/compliance/status/aydinlatma_x", json={"status": "yapildi"})
    # org B kimliğiyle GET → org B'nin durumu yok
    app.dependency_overrides[get_current_identity] = _as_identity(org_id=_ORG_B, user_id=_USER_B)
    try:
        items = {i["key"]: i for g in client.get("/api/compliance/checklist").json()["groups"] for i in g["items"]}
        assert items["aydinlatma_x"]["status"] is None  # A'nın status'ü B'ye sızmıyor
    finally:
        app.dependency_overrides.pop(get_current_identity, None)


# --- kimliksiz 401 ---

@contextlib.contextmanager
def _auth_enforced_client(db_session):
    """Auth zorunlu (dev-bypass kapalı, supabase URL set, dev env) → Bearer yoksa 401.

    environment=development → startup RLS guard postgres'e bağlanmaz (no-op).
    """
    prev = config_module._settings
    config_module._settings = config_module.Settings(
        _env_file=None,
        managed_anthropic_api_key="",
        allowed_origins="http://localhost:3000",
        redis_url="",
        supabase_project_url="https://x.supabase.co",
        auth_dev_bypass=False,
        environment="development",
    )
    reset_redis()

    def _ov():
        yield db_session

    app.dependency_overrides[get_session] = _ov
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        config_module._settings = prev
        reset_redis()


def test_checklist_unauthenticated_401(db_session):
    with _auth_enforced_client(db_session) as c:
        assert c.get("/api/compliance/checklist").status_code == 401


def test_put_unauthenticated_401(db_session):
    with _auth_enforced_client(db_session) as c:
        assert c.put("/api/compliance/status/aydinlatma_x", json={"status": "yapildi"}).status_code == 401
