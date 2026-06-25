"""Prod startup guard: DB bağlantı rolünün RLS'i zorlayıp zorlamadığını doğrular.

FORCE ROW LEVEL SECURITY yalnızca uygulama SUPERUSER veya BYPASSRLS olmayan bir
rolle bağlandığında gerçek anlamda çalışır. Bu modül, prod'da startup sırasında
mevcut DB rolünü sorgular; rol RLS'i bypass edebiliyorsa uygulamanın başlamasını reddeder.
Dev/test (sqlite veya environment != production) ortamlarında tamamen no-op'tur.
"""

from __future__ import annotations

from sqlalchemy import text


def rls_enforcement_violation(
    environment: str,
    is_postgres: bool,
    rolsuper: bool,
    rolbypassrls: bool,
) -> str | None:
    """Saf predikat: RLS zorlama ihlali varsa Türkçe reason string, yoksa None.

    Yalnızca ``environment == "production"`` VE ``is_postgres`` olduğunda denetler;
    aksi halde None döndürür (no-op). Bu, sqlite tabanlı mevcut test paketini
    tamamen etkilemez.

    Args:
        environment: Uygulama ortamı (örn. "development", "production").
        is_postgres: Engine dialect postgresql ise True.
        rolsuper: pg_roles.rolsuper — rol SUPERUSER ise True.
        rolbypassrls: pg_roles.rolbypassrls — rol BYPASSRLS ise True.

    Returns:
        İhlal yoksa None; ihlal varsa insan-okunur Türkçe açıklama string'i.
    """
    if environment != "production" or not is_postgres:
        return None

    if rolsuper:
        return (
            "DB bağlantı rolü SUPERUSER yetkisine sahip: FORCE ROW LEVEL SECURITY "
            "bu rol tarafından sessizce atlanır ve kiracı izolasyonu kırılır. "
            "Prod'da uygulama 'kvkk_app' (NOSUPERUSER NOBYPASSRLS) rolüyle bağlanmalı."
        )

    if rolbypassrls:
        return (
            "DB bağlantı rolü BYPASSRLS yetkisine sahip: FORCE ROW LEVEL SECURITY "
            "bu rol tarafından sessizce atlanır ve kiracı izolasyonu kırılır. "
            "Prod'da uygulama 'kvkk_app' (NOSUPERUSER NOBYPASSRLS) rolüyle bağlanmalı."
        )

    return None


def verify_rls_enforcement(engine, settings) -> None:  # type: ignore[type-arg]
    """DB-bağlı doğrulayıcı: prod+postgresql'de bağlantı rolünü sorgular.

    Yalnızca ``settings.environment == "production"`` VE ``engine.dialect.name == "postgresql"``
    olduğunda bir bağlantı açıp ``pg_roles`` tablosunu sorgular. Rol RLS'i bypass edebiliyorsa
    ``RuntimeError`` fırlatır (uygulama başlamaz — fail-closed, fail-fast). Diğer tüm
    durumlarda (dev, test, sqlite) herhangi bir DB erişimi olmadan erken döner.

    Args:
        engine: SQLAlchemy Engine nesnesi.
        settings: ``environment`` özelliği olan settings nesnesi (app.config.Settings uyumlu).

    Raises:
        RuntimeError: Prod+postgres'te RLS bypass tespit edilirse.
    """
    if settings.environment != "production":
        return
    if engine.dialect.name != "postgresql":
        return

    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        ).one()

    reason = rls_enforcement_violation(
        environment=settings.environment,
        is_postgres=True,
        rolsuper=bool(row.rolsuper),
        rolbypassrls=bool(row.rolbypassrls),
    )
    if reason is not None:
        raise RuntimeError(reason)
