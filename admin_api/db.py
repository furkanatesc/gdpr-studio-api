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


def admin_session() -> Iterator[Session]:
    """FastAPI bağımlılığı: istek başına oturum."""
    sess = sessionmaker(bind=get_admin_engine(), future=True)()
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
