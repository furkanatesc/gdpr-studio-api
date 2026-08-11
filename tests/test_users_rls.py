"""users RLS — membership-EXISTS izolasyon + FORCE (H3). test_audit_rls.py deseni.
Postgres-gated: RLS_TEST_DATABASE_URL yoksa skip. Tek transaction → rollback."""
import os
import uuid

import pytest
from sqlalchemy import create_engine, text

DB_URL = os.getenv("RLS_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DB_URL, reason="RLS yalnız Postgres'te; RLS_TEST_DATABASE_URL gerekli")


def _assert_non_superuser(conn) -> None:
    is_super = conn.execute(
        text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
    ).scalar()
    assert not is_super, "RLS testleri non-superuser (kvkk_app) rolle koşmalı."


def _bypass(conn, on: bool) -> None:
    conn.execute(text("SELECT set_config('app.bypass_rls', :v, true)"), {"v": "on" if on else "off"})


def _ctx(conn, org) -> None:
    conn.execute(text("SELECT set_config('app.current_org_id', :o, true)"), {"o": str(org)})


def _seed_member(conn, org, user, sub, email):
    conn.execute(text("INSERT INTO organizations (id, name) VALUES (:i, 'O')"), {"i": str(org)})
    conn.execute(
        text("INSERT INTO users (id, supabase_user_id, email) VALUES (:i, :s, :e)"),
        {"i": str(user), "s": sub, "e": email},
    )
    conn.execute(
        text("INSERT INTO memberships (id, user_id, org_id, role) VALUES (:i, :u, :o, 'yonetici')"),
        {"i": str(uuid.uuid4()), "u": str(user), "o": str(org)},
    )


def _run(fn):
    eng = create_engine(DB_URL, future=True)
    conn = eng.connect()
    trans = conn.begin()
    try:
        _assert_non_superuser(conn)
        fn(conn)
    finally:
        trans.rollback()
        conn.close()
        eng.dispose()


def test_user_hidden_cross_org_visible_own_org():
    def body(conn):
        org_a, user_a = uuid.uuid4(), uuid.uuid4()
        org_b = uuid.uuid4()
        _bypass(conn, True)
        _seed_member(conn, org_a, user_a, "sub-a", "a@x.io")
        conn.execute(text("INSERT INTO organizations (id, name) VALUES (:i, 'B')"), {"i": str(org_b)})
        _bypass(conn, False)

        _ctx(conn, org_b)  # org B bağlamı → user_a görünmez
        assert conn.execute(text("SELECT count(*) FROM users WHERE id = :u"), {"u": str(user_a)}).scalar() == 0

        _ctx(conn, org_a)  # org A bağlamı → user_a görünür
        assert conn.execute(text("SELECT count(*) FROM users WHERE id = :u"), {"u": str(user_a)}).scalar() == 1
    _run(body)


def test_bypass_sees_all_users():
    def body(conn):
        org_a, user_a = uuid.uuid4(), uuid.uuid4()
        _bypass(conn, True)
        _seed_member(conn, org_a, user_a, "sub-a2", "a2@x.io")
        # org context YOK ama bypass on → görünür (identity çözümü yolu)
        assert conn.execute(text("SELECT count(*) FROM users WHERE id = :u"), {"u": str(user_a)}).scalar() == 1
    _run(body)


def test_insert_requires_bypass():
    def body(conn):
        # bypass on → yeni kullanıcı (membership yok) INSERT geçer
        _bypass(conn, True)
        u1 = uuid.uuid4()
        conn.execute(text("INSERT INTO users (id, supabase_user_id, email) VALUES (:i,'s1','i1@x.io')"), {"i": str(u1)})
        # bypass off + membership yok → INSERT WITH CHECK reddeder
        _bypass(conn, False)
        _ctx(conn, uuid.uuid4())
        sp = conn.begin_nested()
        with pytest.raises(Exception):  # noqa: B017 -- WITH CHECK: membership yok
            conn.execute(text("INSERT INTO users (id, supabase_user_id, email) VALUES (:i,'s2','i2@x.io')"),
                         {"i": str(uuid.uuid4())})
        sp.rollback()
    _run(body)


def test_self_update_in_tenant_context():
    def body(conn):
        org_a, user_a = uuid.uuid4(), uuid.uuid4()
        _bypass(conn, True)
        _seed_member(conn, org_a, user_a, "sub-a3", "a3@x.io")
        _bypass(conn, False)
        _ctx(conn, org_a)  # kendi org üyesi → UPDATE geçer
        conn.execute(text("UPDATE users SET email = 'new@x.io' WHERE id = :u"), {"u": str(user_a)})
        assert conn.execute(text("SELECT email FROM users WHERE id = :u"), {"u": str(user_a)}).scalar() == "new@x.io"
    _run(body)
