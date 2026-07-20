"""Envanter yazımının RLS altında geri okunabilirliği (Postgres-only, kvkk_app).

Prod hatası: import ucu satırları yazıp COMMIT ediyor, sonra özeti okuyordu. Ancak
app.current_org_id set_config(..., true) ile TRANSACTION-LOCAL kurulur; commit onu
sıfırlar → RLS satırları gizler → uç "başarılı" ama "0 kayıt" döner.

SQLite uç testleri bunu ASLA yakalayamaz (tenant_session Postgres değilse GUC kurmaz,
RLS de yoktur). Bu yüzden test PG-gated ve gerçek repository ile koşar.
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.repositories import PostgresProcessRepository

DB_URL = os.getenv("RLS_TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not DB_URL, reason="RLS yalnız Postgres'te; RLS_TEST_DATABASE_URL gerekli")

_ROWS = [
    {"sector": "otel", "kisi_grubu": "Çalışan", "departman": "İK",
     "is_sureci": "Özlük", "alt_surec": "Bordro", "data": {}},
    {"sector": "otel", "kisi_grubu": "Ziyaretçi", "departman": "Güvenlik",
     "is_sureci": "Kamera", "alt_surec": "Kayıt", "data": {}},
]


def _assert_non_superuser(session) -> None:
    is_super = session.execute(
        text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
    ).scalar()
    assert not is_super, (
        "RLS testleri non-superuser rolle (kvkk_app) koşmalı; superuser RLS'i bypass eder "
        "→ test anlamsızca geçer."
    )


def test_envanter_ozeti_commit_ONCESI_okunmali():
    """replace_client → oku → commit sırası doğru; commit sonrası okuma 0 döner."""
    engine = create_engine(DB_URL, future=True)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    org_id, client_id = uuid.uuid4(), uuid.uuid4()
    try:
        _assert_non_superuser(session)

        session.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        session.execute(text("INSERT INTO organizations (id, name, created_at) VALUES (:i, 'RLS Test', now())"),
                        {"i": str(org_id)})
        session.execute(text("INSERT INTO clients (id, org_id, name, created_at) VALUES (:i, :o, 'Müvekkil', now())"),
                        {"i": str(client_id), "o": str(org_id)})
        session.commit()

        # Gerçek istek bağlamı: bypass yok, yalnız org GUC'u (transaction-local).
        session.execute(text("SELECT set_config('app.current_org_id', :o, true)"), {"o": str(org_id)})
        repo = PostgresProcessRepository(session)
        repo.replace_client(org_id, client_id, _ROWS)

        onces = len(repo.client_processes(client_id))
        assert onces == len(_ROWS), f"commit ÖNCESİ okuma satırları görmeli, {onces} gördü"

        session.commit()  # GUC burada sıfırlanır

        sonra = len(repo.client_processes(client_id))
        assert sonra == 0, (
            f"commit SONRASI okuma RLS nedeniyle 0 dönmeli (görülen: {sonra}). "
            "Bu testin amacı tehlikeyi sabitlemek: özet commit'ten ÖNCE okunmalı."
        )

        # Satırlar gerçekten YAZILDI — görünmüyor olmaları yalnızca RLS bağlamı kaybı.
        session.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        yazilan = session.execute(
            text("SELECT count(*) FROM processes WHERE client_id = :c"), {"c": str(client_id)}
        ).scalar()
        assert yazilan == len(_ROWS), "satırlar yazılmalıydı; sorun okuma bağlamı, yazma değil"
    finally:
        session.rollback()
        session.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        session.execute(text("DELETE FROM processes WHERE client_id = :c"), {"c": str(client_id)})
        session.execute(text("DELETE FROM clients WHERE id = :c"), {"c": str(client_id)})
        session.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": str(org_id)})
        session.commit()
        session.close()
        engine.dispose()
