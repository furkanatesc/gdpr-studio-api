from __future__ import annotations

import uuid

from app.models import Process


def _bootstrap_client(client_fresh, sector="otel"):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    return client_fresh.post("/api/clients", json={"name": "Otel A.S.", "sector": sector}).json()["id"]


def _seed_global_process(db_session, **data):
    db_session.add(Process(sector="otel", kisi_grubu="Calisan", departman="IK",
                           is_sureci="Ozluk", alt_surec="Bordro",
                           org_id=None, client_id=None, data=data))
    db_session.commit()


ROW_BOS_SAKLAMA = {"departman": "IK", "is_sureci": "Ozluk", "alt_surec": "Bordro",
                   "kisi_grubu": "Calisan", "kategoriler": ["Kimlik"], "amaclar": ["Bordro"]}


def test_suggestions_requires_auth(client_no_account):
    r = client_no_account.get(f"/api/clients/{uuid.uuid4()}/inventory/suggestions")
    assert r.status_code in (401, 403)


def test_suggestions_unknown_client_404(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Buro"})
    r = client_fresh.get(f"/api/clients/{uuid.uuid4()}/inventory/suggestions")
    assert r.status_code == 404


def test_suggestions_empty_inventory(client_fresh):
    cid = _bootstrap_client(client_fresh)
    r = client_fresh.get(f"/api/clients/{cid}/inventory/suggestions")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"bosSlot": 0, "tamlik": None, "rows": []}


def test_suggestions_surface_grounding_for_empty_field(client_fresh, db_session):
    _seed_global_process(db_session, kategoriler=["Kimlik"], saklama_sureleri=["10 yil"])
    cid = _bootstrap_client(client_fresh)
    assert client_fresh.put(f"/api/clients/{cid}/inventory",
                            json={"rows": [ROW_BOS_SAKLAMA]}).status_code == 200
    r = client_fresh.get(f"/api/clients/{cid}/inventory/suggestions")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"][0]["oneriler"]["saklama_sureleri"] == ["10 yil"]
    assert body["rows"][0]["elleAlanlar"] == ["aktarim"]
    assert body["rows"][0]["kisiGrubu"] == "Calisan"
    # bosSlot: kategoriler|veri_turleri dolu, amaclar dolu, kisi_grubu dolu;
    # hukuki_sebepler + saklama_sureleri + aktarim bos = 3
    assert body["bosSlot"] == 3
    assert 0.0 < body["tamlik"] < 1.0
