"""usage_counters RLS testi — akis sayiminin commit-sonrasi org baglamini toparlamasi.

Sayim/maliyet 2026-07-24'te Stripe'tan ayrildi (billing_enabled kapaliyken de yazilir).
Bu, daha once prod'da HIC calismamis bir yazma yolunu FORCE RLS altinda aktif hale getirir:
`reserve_generation_usage` commit eder → `app.current_org_id` (transaction-local) SIFIRLANIR →
`settle_generation_usage`'in add_cost'u GUC'siz kalirsa RLS ile patlar. C1 dersinin ayni sinifi.
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DB_URL = os.getenv("RLS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="RLS yalniz Postgres'te; RLS_TEST_DATABASE_URL gerekli")


def _assert_non_superuser(conn) -> None:
    is_super = conn.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar()
    assert not is_super, "RLS testleri kvkk_app (non-superuser) ile kosmali."


def test_reserve_then_settle_survives_rls_after_commit():
    import app.config as config_module
    from app.billing.entitlement import current_period
    from app.billing.pricing import cost_micros
    from app.billing.quota import reserve_generation_usage, settle_generation_usage

    settings = config_module.Settings(_env_file=None, stripe_secret_key="")
    assert settings.billing_enabled is False  # prod durumu: Stripe kurulu degil

    eng = create_engine(DB_URL, future=True)
    org_id = uuid.uuid4()
    try:
        with eng.begin() as conn:
            _assert_non_superuser(conn)
            conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
            conn.execute(
                text("INSERT INTO organizations (id, name) VALUES (:id, 'Usage RLS Org')"),
                {"id": str(org_id)},
            )
        # Blok commit'te bitti: bir sonraki oturum GUC'siz (fail-closed) baslar.

        conn = eng.connect()
        session = sessionmaker(bind=conn, future=True)()
        try:
            reserved = reserve_generation_usage(
                session, settings, org_id, model="claude-sonnet-4-6", byok=False,
            )
            # reserve commit etti → GUC sifirlandi; settle kendi baglamini kurmali.
            settle_generation_usage(
                session, settings, org_id,
                model="claude-sonnet-4-6", input_tokens=100, output_tokens=200,
                byok=False, reserved_micros=reserved,
            )
        finally:
            session.close()
            conn.close()

        try:
            with eng.begin() as conn:
                conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
                row = conn.execute(
                    text(
                        "SELECT doc_count, cost_micros FROM usage_counters "
                        "WHERE org_id = :o AND period = :p"
                    ),
                    {"o": str(org_id), "p": current_period()},
                ).fetchone()
            assert row is not None, "rezervasyon yazilamadi (org GUC'si kurulmamis)"
            assert row[0] == 1, f"dokuman sayimi 1 olmali, {row[0]} geldi"
            assert row[1] == cost_micros("claude-sonnet-4-6", 100, 200), (
                "mahsuplasma yazilamadi: settle commit-sonrasi org baglamini kurmuyor olabilir"
            )
        finally:
            with eng.begin() as conn:
                conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
                conn.execute(text("DELETE FROM usage_counters WHERE org_id = :o"), {"o": str(org_id)})
                conn.execute(text("DELETE FROM organizations WHERE id = :o"), {"o": str(org_id)})
    finally:
        eng.dispose()
