"""apply_seed gerçek Postgres/RLS altında (kvkk_app) doğru çalışır.

BLOCKER doğrulaması: seed kvkk_app rolüyle koşar; processes FORCE RLS'li (0010) ve
write politikasında `org_id IS NULL` istisnası YOK. Bypass olmadan global satır
INSERT'i WITH CHECK'e takılır → seed çöker. apply_seed begin_provisioning ile bypass
açar. Bu test o yolu gerçek RLS'te sınar (SQLite testleri RLS'e kördür).

Ayrıca kanıtlar: seed müvekkil envanterini (org_id/client_id dolu) SİLMEZ.
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.models import Process
from app.seed import apply_seed

DB_URL = os.getenv("RLS_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not DB_URL, reason="RLS yalnız Postgres'te; RLS_TEST_DATABASE_URL gerekli")

_GLOBAL_PROC = [{"sector": "otel", "kisi_grubu": "Çalışan", "departman": "İK",
                 "is_sureci": "Özlük", "alt_surec": "Bordro", "data": {}}]


def _assert_non_superuser(session) -> None:
    is_super = session.execute(
        text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
    ).scalar()
    assert not is_super, "kvkk_app non-superuser olmalı; superuser RLS'i bypass eder → test vacuous."


def test_apply_seed_kvkk_app_rolunde_global_yazar_muvekkili_korur():
    engine = create_engine(DB_URL, future=True)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    org, client = uuid.uuid4(), uuid.uuid4()
    try:
        _assert_non_superuser(session)

        # Ön hazırlık: bir müvekkil envanteri satırı (bypass ile kur).
        session.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        session.execute(text("INSERT INTO organizations (id, name, created_at) VALUES (:i,'Seed RLS',now())"),
                        {"i": str(org)})
        session.execute(text("INSERT INTO clients (id, org_id, name, created_at) VALUES (:i,:o,'M',now())"),
                        {"i": str(client), "o": str(org)})
        session.execute(text(
            "INSERT INTO processes (id, sector, kisi_grubu, departman, is_sureci, alt_surec, data, org_id, client_id) "
            "VALUES (gen_random_uuid(),'otel','Ziyaretçi','Güvenlik','Kamera','Kayıt','{}'::jsonb,:o,:c)"),
            {"o": str(org), "c": str(client)})
        session.commit()

        # Bypass'ı kapat → gerçek seed bağlamı (kvkk_app, org bağlamı YOK).
        session.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))

        # apply_seed kendi begin_provisioning'iyle bypass açar; bypass olmasa insert çökerdi.
        counts = apply_seed(session, categories={}, rules=[], processes=_GLOBAL_PROC,
                            measures=[], requirements=[])
        assert counts["surec"] == 1
        session.commit()

        # Müvekkil satırı hayatta mı + global yenilendi mi (bypass ile say).
        session.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        muvekkil = session.scalars(select(Process).where(Process.client_id == client)).all()
        assert len(muvekkil) == 1, "müvekkil envanteri seed'den sağ çıkmalı"
        globaller = session.scalars(
            select(Process).where(Process.org_id.is_(None), Process.client_id.is_(None))
        ).all()
        assert len(globaller) == 1 and globaller[0].kisi_grubu == "Çalışan", "global grounding yenilenmeli"
    finally:
        session.rollback()
        session.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        session.execute(text("DELETE FROM processes WHERE client_id = :c OR (org_id IS NULL AND client_id IS NULL)"),
                        {"c": str(client)})
        session.execute(text("DELETE FROM clients WHERE id = :c"), {"c": str(client)})
        session.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": str(org)})
        session.commit()
        session.close()
        engine.dispose()
