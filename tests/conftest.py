"""API entegrasyon testleri için ortak fixture'lar.

İzole, altyapısız: gerçek Postgres yerine in-memory SQLite (StaticPool ile tek
paylaşımlı bağlantı), `get_session` bağımlılığı override edilir ve ayar singleton'ı
managed-anahtarsız/`.env`'siz bir Settings ile değiştirilir (lokal `.env`'deki managed
anahtarın testleri gerçek API'ye çağırmasını önler).
"""

from __future__ import annotations

import contextlib
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.config as config_module
from app.auth.identity import Identity, get_current_identity
from app.db import Base, get_session
from app.email.sender import reset_email_sender
from app.main import app
from app.models import BusinessRule, Category
from app.redis_client import reset_redis

_DEV_IDENTITY = Identity(
    user_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
    org_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
    role="yonetici",
    email="dev@kvkkyonetim.local",
)

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


@contextlib.contextmanager
def _dev_bypass_client(db_session):
    """DRY yardımcı: dev-bypass ayarlarını kur, get_session'ı override et, TestClient döndür.

    Hem client_fresh hem client_no_account bu context-manager'ı paylaşır; kurulum/teardown
    mantığı tek yerde tutulur. Ayrılan tek şey: çağıran fixture bootstrap yapıp yapmadığıdır.
    """
    prev_settings = config_module._settings
    config_module._settings = config_module.Settings(
        _env_file=None,
        managed_anthropic_api_key="",
        allowed_origins="http://localhost:3000",
        redis_url="",
        supabase_project_url="",  # dev-bypass aktif: auth olmadan dev claims döner
        auth_dev_bypass=True,
        environment="development",
        invite_secret="test-secret",
    )
    reset_redis()
    reset_email_sender()

    def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    # get_current_identity override edilmez — gerçek DB çözümlemesi çalışır
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        config_module._settings = prev_settings
        reset_redis()
        reset_email_sender()


@pytest.fixture()
def client(db_session):
    # Lokal .env'deki managed anahtarı devre dışı bırak → anahtarsız üretim yolu 400 verir.
    prev_settings = config_module._settings
    config_module._settings = config_module.Settings(
        _env_file=None,
        managed_anthropic_api_key="",
        allowed_origins="http://localhost:3000",
        redis_url="",  # Redis testlerde devre dışı → rate-limit fail-open, cache miss
    )
    reset_redis()  # ayar değişti → singleton yeniden değerlendirilsin

    def _override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = _override_get_session
    app.dependency_overrides[get_current_identity] = lambda: _DEV_IDENTITY
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.clear()
        config_module._settings = prev_settings
        reset_redis()


@pytest.fixture()
def accept_as(client_fresh, monkeypatch):
    """Farklı bir kimlik olarak davet kabul et.

    accept endpoint _claims_from_request'i doğrudan çağırır (FastAPI Depends üzerinden değil),
    bu nedenle dependency_overrides çalışmaz. Bunun yerine modül içindeki fonksiyonu monkeypatch
    ile geçici olarak değiştiririz; monkeypatch test sonrası otomatik geri alır.
    """
    import app.modules.invitations as invmod
    from app.auth.jwt import AuthClaims

    def _accept(sub: str, email: str, token: str):
        monkeypatch.setattr(invmod, "_claims_from_request", lambda request: AuthClaims(sub=sub, email=email))
        return client_fresh.post(f"/api/invitations/{token}/accept")

    return _accept


@pytest.fixture()
def client_fresh(db_session):
    """dev-bypass ile DB'den kimlik çözümlenir; bootstrap testi için temiz DB.

    supabase_project_url="" + auth_dev_bypass=True olduğundan _claims_from_request dev claims
    döndürür (sub="dev-user", email="dev@kvkkyonetim.local"). DB temiz (sadece kategori/kural
    seed'i; users/orgs yok). bootstrap/me akışı gerçek DB çözümlemesini test eder.
    """
    with _dev_bypass_client(db_session) as c:
        yield c


@pytest.fixture()
def client_no_account(db_session):
    """dev-bypass aktif, DB temiz, bootstrap ÇAĞRILMADI → /me 403 döndürür.

    client_fresh ile özdeş kurulum; fixture adı "kullanıcı yok → 403" testinin amacını açıklar.
    """
    with _dev_bypass_client(db_session) as c:
        yield c
