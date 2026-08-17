"""admin-api ayarları (ortam değişkenlerinden). Kiracı `app.config.Settings`'den bağımsız."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class AdminSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    environment: str = "development"

    # Veritabanı — kvkk_admin_ro rolüyle bağlanır (bkz. migration 0020).
    admin_database_url: str = ""
    expected_migration_head: str = "0020"
    admin_pool_size: int = 3
    admin_pool_max_overflow: int = 2

    # Auth — staff Supabase projesi kiracı projesinden AYRI; aud farklı.
    admin_supabase_project_url: str = ""
    admin_supabase_jwt_aud: str = "platform-admin"
    admin_jwks_timeout_s: int = 10

    # H5 gate — varsayılan KAPALI (yasal/hukuki onay öncesi hiçbir platform-admin uç aktif olmaz).
    h5_legal_ready: bool = False

    # IP allowlist — altyapı (ör. Railway private networking) zorunlu kılar; uygulama tarafı savunma derinliği.
    admin_allowed_ips: str = ""

    @property
    def admin_supabase_issuer(self) -> str:
        return f"{self.admin_supabase_project_url.rstrip('/')}/auth/v1"

    @property
    def admin_jwks_url(self) -> str:
        return f"{self.admin_supabase_project_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


@lru_cache
def get_admin_settings() -> AdminSettings:
    return AdminSettings()
