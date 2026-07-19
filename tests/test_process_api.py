"""Süreç API'si + sektör profili. client_fresh dev-bypass ile kimliği DB'den çözer."""

from app.models import Organization, Process


def _seed_processes(db_session):
    db_session.add_all([
        Process(sector="sirket", kisi_grubu="Çalışan", departman="İK",
                is_sureci="İşe Giriş", alt_surec="Kimlik teyidi",
                data={"kategoriler": ["Kimlik"], "saklama_sureleri": ["10 yıl"]}),
        Process(sector="sirket", kisi_grubu="Ziyaretçi", departman="GÜVENLİK",
                is_sureci="Giriş", alt_surec="Kayıt", data={"kategoriler": ["Kimlik"]}),
        Process(sector="otel", kisi_grubu="Tedarikçi Çalışanı", departman="TEKNİK",
                is_sureci="Cihaz", alt_surec="Kalibrasyon", data={}),
    ])
    db_session.commit()


def _set_sector(db_session, sector):
    org = db_session.query(Organization).first()
    org.sector = sector
    db_session.commit()


def test_person_groups_empty_without_sector(client_fresh, db_session):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    _seed_processes(db_session)
    r = client_fresh.get("/api/processes/person-groups")
    assert r.status_code == 200
    assert r.json() == []  # sektör yok → boş (uydurma yok)


def test_person_groups_filtered_by_org_sector(client_fresh, db_session):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    _seed_processes(db_session)
    _set_sector(db_session, "sirket")
    r = client_fresh.get("/api/processes/person-groups")
    assert r.status_code == 200
    assert r.json() == ["Çalışan", "Ziyaretçi"]  # otel sızmaz


def test_patch_org_sector_updates_and_returns_identity(client_fresh, db_session):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    r = client_fresh.patch("/api/auth/org", json={"sector": "otel"})
    assert r.status_code == 200, r.text
    assert r.json()["sector"] == "otel"
    assert client_fresh.get("/api/auth/me").json()["sector"] == "otel"


def test_patch_org_rejects_unknown_sector(client_fresh):
    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    assert client_fresh.patch("/api/auth/org", json={"sector": "uzay_madenciligi"}).status_code == 422


def test_patch_org_sector_requires_admin(client_fresh):
    import uuid

    from app.auth.identity import Identity, get_current_identity
    from app.main import app

    client_fresh.post("/api/auth/bootstrap", json={"orgName": "Acme"})
    app.dependency_overrides[get_current_identity] = lambda: Identity(
        user_id=uuid.uuid4(), org_id=uuid.uuid4(), role="avukat", email="a@b.com"
    )
    try:
        assert client_fresh.patch("/api/auth/org", json={"sector": "otel"}).status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_identity, None)
