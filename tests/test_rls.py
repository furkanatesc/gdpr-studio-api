"""Gerçek iki-org RLS izolasyon testi (Postgres-only, FORCE altında).

DİKKAT: Bu test NON-SUPERUSER rolle (kvkk_app, NOSUPERUSER NOBYPASSRLS) koşmalıdır.
FORCE ROW LEVEL SECURITY tablo-OWNER'ı RLS'e tabi kılar ama bir SUPERUSER'ı ASLA;
owner rolü kvkk postgres imajında superuser olduğundan FORCE onu kapsamaz ve test
vacuous geçer. Bu yüzden RLS_TEST_DATABASE_URL kvkk_app'e yönlendirilmeli; aşağıdaki
_assert_non_superuser guard'ı yanlış role karşı koşmayı erkenden yakalar.

kvkk_app altında bu test vacuous değil, izolasyonu GERÇEK kanıtlar:
  - app.current_org_id=A iken yalnız A'nın üyeliği görünür (B gizli),
  - app.bypass_rls='on' iken her iki üyelik de görünür (provisioning yolu).

Test tüm verisini tek transaction içinde kurar ve sonunda ROLLBACK eder →
dev DB'de kalıcı kirlilik bırakmaz.
"""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text

DB_URL = os.getenv("RLS_TEST_DATABASE_URL")  # ör. postgresql+psycopg://kvkk:kvkk@localhost:5432/kvkk

pytestmark = pytest.mark.skipif(not DB_URL, reason="RLS yalnız Postgres'te; RLS_TEST_DATABASE_URL gerekli")


def _assert_non_superuser(conn) -> None:
    """RLS testi superuser ile koşarsa FORCE bypass edilir ve test vacuous geçer."""
    is_super = conn.execute(
        text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
    ).scalar()
    assert not is_super, (
        "RLS testleri non-superuser rolle (kvkk_app) koşmalı; superuser RLS'i bypass "
        "eder → test anlamsızca geçer. RLS_TEST_DATABASE_URL'i kvkk_app'e yönlendirin."
    )


def _count_memberships(conn) -> int:
    return conn.execute(text("SELECT count(*) FROM memberships")).scalar()


def _count_memberships_in(conn, org_ids) -> int:
    return conn.execute(
        text("SELECT count(*) FROM memberships WHERE org_id = ANY(:oids)"),
        {"oids": [str(o) for o in org_ids]},
    ).scalar()


def test_force_rls_isolates_orgs_and_bypass_sees_all():
    eng = create_engine(DB_URL, future=True)
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    user_a, user_b = uuid.uuid4(), uuid.uuid4()

    # Tek transaction: kur → doğrula → rollback (kalıcı kirlilik yok).
    conn = eng.connect()
    trans = conn.begin()
    try:
        _assert_non_superuser(conn)
        # 1) bypass açıkken iki org + ikisine birer membership ekle.
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        for oid, name in [(org_a, "RLS Test A"), (org_b, "RLS Test B")]:
            conn.execute(
                text("INSERT INTO organizations (id, name) VALUES (:id, :name)"),
                {"id": oid, "name": name},
            )
        conn.execute(
            text("INSERT INTO users (id, supabase_user_id, email) VALUES (:id, :sub, :em)"),
            {"id": user_a, "sub": f"rls-a-{user_a}", "em": "rls-a@test.local"},
        )
        conn.execute(
            text("INSERT INTO users (id, supabase_user_id, email) VALUES (:id, :sub, :em)"),
            {"id": user_b, "sub": f"rls-b-{user_b}", "em": "rls-b@test.local"},
        )
        conn.execute(
            text(
                "INSERT INTO memberships (id, user_id, org_id, role) "
                "VALUES (:id, :uid, :oid, 'yonetici')"
            ),
            {"id": uuid.uuid4(), "uid": user_a, "oid": org_a},
        )
        conn.execute(
            text(
                "INSERT INTO memberships (id, user_id, org_id, role) "
                "VALUES (:id, :uid, :oid, 'yonetici')"
            ),
            {"id": uuid.uuid4(), "uid": user_b, "oid": org_b},
        )

        # 2) İZOLASYON: bypass KAPALI, org A bağlamı → yalnız A'nınki görünür.
        # (DB'de başka org'ların verisi olabilir; bizim iki test org'umuz üzerinden
        # ölçüyoruz: A bağlamında bizim org'larımızdan yalnız A'nınki sayılmalı, B gizli.)
        conn.execute(text("SELECT set_config('app.bypass_rls', 'off', true)"))
        conn.execute(
            text("SELECT set_config('app.current_org_id', :oid, true)"),
            {"oid": str(org_a)},
        )
        assert _count_memberships_in(conn, [org_a, org_b]) == 1  # B gizli → izolasyon kanıtlandı

        # 3) BYPASS: provisioning bağlamı → her iki test üyeliği de görünür.
        conn.execute(text("SELECT set_config('app.bypass_rls', 'on', true)"))
        assert _count_memberships_in(conn, [org_a, org_b]) == 2
    finally:
        trans.rollback()
        conn.close()
        eng.dispose()


def test_force_rls_fail_closed_without_guc():
    """GUC hiç set edilmemiş (NULL) → policy false → sıfır satır (fail-closed).

    Not: set_config(..., '') GUC'u boş STRING yapar ve ''::uuid hata verir; gerçek
    fail-closed durumu GUC'un hiç set edilmemesi (NULL) hâlidir — bu yüzden ayrı,
    GUC'a hiç dokunmayan taze bir transaction kullanırız.
    """
    eng = create_engine(DB_URL, future=True)
    conn = eng.connect()
    trans = conn.begin()
    try:
        _assert_non_superuser(conn)
        # Hiçbir GUC set edilmedi → current_setting(..., true)=NULL → NULL::uuid=NULL → false.
        assert _count_memberships(conn) == 0
    finally:
        trans.rollback()
        conn.close()
        eng.dispose()
