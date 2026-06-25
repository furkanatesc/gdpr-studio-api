"""Startup guard testleri: saf predikat + no-op yolları.

Postgres GEREKTİRMEZ — saf fonksiyon ve fake engine ile çalışır.
"""

from __future__ import annotations

import types

from app.auth.startup_guard import rls_enforcement_violation, verify_rls_enforcement

# ---------------------------------------------------------------------------
# Saf predikat matrisi
# ---------------------------------------------------------------------------


def test_development_always_none():
    """Development ortamında her kombinasyon None döndürmeli."""
    assert rls_enforcement_violation("development", True, True, True) is None
    assert rls_enforcement_violation("development", True, False, False) is None


def test_production_not_postgres_none():
    """Production + sqlite (is_postgres=False) → None (no-op)."""
    assert rls_enforcement_violation("production", False, True, True) is None


def test_production_postgres_superuser_returns_reason():
    """Production + postgres + rolsuper=True → reason string, 'SUPERUSER' içermeli."""
    reason = rls_enforcement_violation("production", True, True, False)
    assert reason is not None
    assert "SUPERUSER" in reason


def test_production_postgres_bypassrls_returns_reason():
    """Production + postgres + rolbypassrls=True → reason string, 'BYPASSRLS' içermeli."""
    reason = rls_enforcement_violation("production", True, False, True)
    assert reason is not None
    assert "BYPASSRLS" in reason


def test_production_postgres_both_false_none():
    """Production + postgres + ikisi de False → None (güvenli rol)."""
    assert rls_enforcement_violation("production", True, False, False) is None


# ---------------------------------------------------------------------------
# verify_rls_enforcement: non-prod/non-postgres → no-op (DB sorgusu YOK)
# ---------------------------------------------------------------------------


def _fake_engine(dialect_name: str):
    """Gerçek bağlantı açmayan sahte engine nesnesi."""
    dialect = types.SimpleNamespace(name=dialect_name)
    return types.SimpleNamespace(dialect=dialect)


def _fake_settings(environment: str):
    return types.SimpleNamespace(environment=environment)


def test_verify_noop_for_non_production_postgres():
    """Development + postgresql dialect → gerçek sorgu olmadan return."""
    engine = _fake_engine("postgresql")
    settings = _fake_settings("development")
    # Bağlantı açılırsa AttributeError (fake engine connect() yok) → bu da başarısızlık.
    # Hata yoksa no-op doğrulandı.
    verify_rls_enforcement(engine, settings)  # type: ignore[arg-type]


def test_verify_noop_for_production_sqlite():
    """Production + sqlite dialect → gerçek sorgu olmadan return."""
    engine = _fake_engine("sqlite")
    settings = _fake_settings("production")
    verify_rls_enforcement(engine, settings)  # type: ignore[arg-type]


def test_verify_noop_for_development_sqlite():
    """Development + sqlite (test ortamı) → no-op."""
    engine = _fake_engine("sqlite")
    settings = _fake_settings("development")
    verify_rls_enforcement(engine, settings)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# verify_rls_enforcement: prod+postgres, pg_roles boş satır → RuntimeError
# ---------------------------------------------------------------------------


def _fake_engine_with_result(dialect_name: str, one_or_none_result):
    """Sorgu sonucu kontrol edilebilen sahte engine nesnesi."""

    class FakeResult:
        def one_or_none(self):
            return one_or_none_result

    class FakeConn:
        def execute(self, _query):
            return FakeResult()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class FakeEngine:
        dialect = types.SimpleNamespace(name=dialect_name)

        def connect(self):
            return FakeConn()

    return FakeEngine()


def test_verify_raises_when_pg_roles_returns_no_row():
    """Prod+postgresql'de pg_roles sorgusu satır döndürmezse RuntimeError fırlatılmalı (fail-closed)."""
    import pytest

    engine = _fake_engine_with_result("postgresql", None)
    settings = _fake_settings("production")
    with pytest.raises(RuntimeError, match="pg_roles'te bulunamadı"):
        verify_rls_enforcement(engine, settings)  # type: ignore[arg-type]
