"""API entegrasyon testleri için ortak fixture'lar.

İzole, altyapısız: gerçek Postgres yerine in-memory SQLite (StaticPool ile tek
paylaşımlı bağlantı), `get_session` bağımlılığı override edilir ve ayar singleton'ı
managed-anahtarsız/`.env`'siz bir Settings ile değiştirilir (lokal `.env`'deki managed
anahtarın testleri gerçek API'ye çağırmasını önler).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.config as config_module
from app.db import Base, get_session
from app.main import app
from app.models import BusinessRule, Category

# /api/categories ve grounding için temsili minimum seed (gerçek kategori adları).
_SEED_CATEGORIES = [
    Category(name="Kimlik", data={"veri_turu": ["ad", "soyad"], "hukuki_sebepler": ["5/2-ç"]}),
    Category(name="İletişim", data={"veri_turu": ["e-posta"], "hukuki_sebepler": ["5/2-f"]}),
    Category(name="Sağlık Bilgileri", data={"veri_turu": ["tanı"], "hukuki_sebepler": ["6/3"]}),
]
_SEED_RULES = [
    BusinessRule(dokuman_turu="Tümü", kural_metni="Her belgede avukat onayı uyarısı bulunmalı."),
    BusinessRule(dokuman_turu="aydinlatma", kural_metni="Veri sorumlusu kimliği yer almalı."),
]


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # tek bağlantı → create_all + sorgular aynı in-memory DB'yi görür
        future=True,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestSession()
    session.add_all([Category(name=c.name, data=c.data) for c in _SEED_CATEGORIES])
    session.add_all([BusinessRule(dokuman_turu=r.dokuman_turu, kural_metni=r.kural_metni) for r in _SEED_RULES])
    session.commit()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture()
def client(db_session):
    # Lokal .env'deki managed anahtarı devre dışı bırak → anahtarsız üretim yolu 400 verir.
    prev_settings = config_module._settings
    config_module._settings = config_module.Settings(
        _env_file=None,
        managed_anthropic_api_key="",
        allowed_origins="http://localhost:3000",
    )

    def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        config_module._settings = prev_settings
