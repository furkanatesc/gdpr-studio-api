"""admin-api SQLAlchemy motoru — sınırlı havuz + açılışta rol/migrasyon başı doğrulama.

Tek göçmen (migrator) backend `start.sh`'tir; admin-api ASLA `alembic upgrade` çalıştırmaz,
yalnızca beklenen migrasyon başını ve rolün süper-kullanıcı/RLS-bypass OLMADIĞINI doğrular.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import normalize_pg_url

from .config import AdminSettings, get_admin_settings

_engine = None
_session_factory = None


def get_admin_engine():
    global _engine
    if _engine is None:
        s = get_admin_settings()
        _engine = create_engine(
            normalize_pg_url(s.admin_database_url),
            pool_pre_ping=True,
            pool_size=s.admin_pool_size,
            max_overflow=s.admin_pool_max_overflow,
            future=True,
        )
    return _engine


def _get_session_factory():
    """Motor gibi sessionmaker da tek sefer kurulur (istek başına yeniden kurma yok)."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_admin_engine(), future=True)
    return _session_factory


def admin_session() -> Iterator[Session]:
    """FastAPI bağımlılığı: istek başına oturum."""
    sess = _get_session_factory()()
    try:
        yield sess
    finally:
        sess.close()


def verify_admin_role_and_head(engine, settings: AdminSettings) -> None:
    """Postgres'te: bağlanan rolün NOSUPERUSER/NOBYPASSRLS olduğunu ve migrasyon başının
    beklenenle eşleştiğini doğrular. Postgres dışı dialect'lerde no-op (dev/test SQLite)."""
    if engine.dialect.name != "postgresql":
        return
    with engine.connect() as c:
        r = c.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()
        if r.rolsuper or r.rolbypassrls:
            raise RuntimeError("admin-api must connect as a NOBYPASSRLS/NOSUPERUSER role")
        head = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if head != settings.expected_migration_head:
            raise RuntimeError(
                f"admin-api expects migration head {settings.expected_migration_head}, found {head}"
            )


def assert_bypass_off(session: Session) -> None:
    """Defensive: a scoped impersonation read must NEVER run with app.bypass_rls='on'
    (a dirty bypass window leaks ALL tenants). Postgres-only check; no-op on sqlite (no RLS)."""
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        val = session.execute(text("SELECT current_setting('app.bypass_rls', true)")).scalar()
        if val == "on":
            raise RuntimeError("bypass_rls is ON during impersonation read — aborting (isolation breach)")
