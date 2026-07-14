"""usage_counters artışının ATOMİKLİĞİ — H1-2 (mimari review P1).

Kaçak: `SELECT` → Python'da `+= 1` → `UPDATE` deseni READ COMMITTED altında lost-update
üretir; eşzamanlı iki üretim aynı N'i okuyup ikisi de N+1 yazar → bir artış kaybolur ve
ücretsiz tavan / maliyet bütçesi sessizce aşılır.

İki katman:
  1. SQL-şekli (deterministik, dialect'ten bağımsız): artış TEK ifadede, `ON CONFLICT
     DO UPDATE SET col = col + delta` ile yapılıyor mu — yani read-modify-write yok mu?
  2. Gerçek Postgres'te eşzamanlı iki yazar (regresyon guard'ı; RLS_TEST_DATABASE_URL gerekli).
"""

from __future__ import annotations

import os
import threading
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.billing.repositories import UsageRepository

PERIOD = "2026-07"


def test_increment_emits_single_atomic_upsert(db_session):
    """Artış tek ifade: INSERT ... ON CONFLICT DO UPDATE SET doc_count = doc_count + 1."""
    statements: list[str] = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        statements.append(" ".join(statement.split()).lower())

    engine = db_session.get_bind()
    from sqlalchemy import event

    event.listen(engine, "before_cursor_execute", _record)
    try:
        UsageRepository(db_session).increment(uuid.uuid4(), PERIOD)
    finally:
        event.remove(engine, "before_cursor_execute", _record)

    writes = [s for s in statements if s.startswith("insert") or s.startswith("update")]
    assert len(writes) == 1, f"artış tek ifade olmalı, görülen: {writes}"
    upsert = writes[0]
    assert "on conflict" in upsert
    assert "do update set doc_count = (usage_counters.doc_count + " in upsert  # sunucu tarafı artış
    # Okuma-sonra-yazma (SELECT ... FROM usage_counters) yolu tamamen kalkmalı:
    assert not any("select" in s and "from usage_counters" in s for s in statements)


def test_add_cost_accumulates_atomically(db_session):
    """Maliyet/token birikimi de tek ifadede toplanır (negatif delta = mahsup)."""
    repo = UsageRepository(db_session)
    org = uuid.uuid4()
    repo.add_cost(org, PERIOD, 100, 200, 5_000)
    repo.add_cost(org, PERIOD, 10, 20, -1_000)  # rezervasyon mahsubu negatif olabilir
    db_session.commit()

    assert repo.get_cost(org, PERIOD) == 4_000
    row = repo._row(org, PERIOD)
    assert row.input_tokens == 110
    assert row.output_tokens == 220
    assert row.doc_count == 0  # add_cost doküman saymaz


# ── Gerçek Postgres: eşzamanlı iki yazar (regresyon guard'ı) ──────────────────────────
DB_URL = os.getenv("RLS_TEST_DATABASE_URL")


@pytest.mark.skipif(not DB_URL, reason="Eşzamanlılık testi gerçek Postgres ister")
def test_concurrent_increments_do_not_lose_updates():
    """İki eşzamanlı üretim → iki artış. Read-modify-write'ta biri kaybolabilirdi."""
    engine = create_engine(DB_URL, future=True)
    org = uuid.uuid4()
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    with engine.begin() as conn:
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        conn.execute(
            text("INSERT INTO organizations (id, name) VALUES (:id, 'Atomik Sayaç Testi')"),
            {"id": org},
        )

    barrier = threading.Barrier(2, timeout=10)
    errors: list[Exception] = []

    def _worker() -> None:
        session = TestSession()
        try:
            session.execute(
                text("SELECT set_config('app.current_org_id', :oid, true)"), {"oid": str(org)}
            )
            repo = UsageRepository(session)
            barrier.wait()  # iki yazar aynı anda vursun
            repo.increment(org, PERIOD)
            repo.add_cost(org, PERIOD, 100, 200, 5_000)
            session.commit()
        except Exception as exc:  # noqa: BLE001 — ana thread'e taşı
            errors.append(exc)
        finally:
            session.close()

    threads = [threading.Thread(target=_worker) for _ in range(2)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        assert not errors, f"eşzamanlı yazarlar hata verdi: {errors}"
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
            row = conn.execute(
                text(
                    "SELECT doc_count, cost_micros, input_tokens, output_tokens "
                    "FROM usage_counters WHERE org_id = :oid AND period = :p"
                ),
                {"oid": org, "p": PERIOD},
            ).one()
        assert row.doc_count == 2  # lost-update olsaydı 1 kalabilirdi
        assert row.cost_micros == 10_000
        assert row.input_tokens == 200
        assert row.output_tokens == 400
    finally:
        with engine.begin() as conn:
            conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
            conn.execute(text("DELETE FROM usage_counters WHERE org_id = :oid"), {"oid": org})
            conn.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": org})
        engine.dispose()
