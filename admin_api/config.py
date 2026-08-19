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

    # Metrics rollup job — kvkk_admin_ro DEĞİL, ayrı en-az-yetki `kvkk_metrics_job` rolüyle
    # bağlanır (bkz. migration 0020: bu role yalnız platform_metrics_daily'ye INSERT/UPDATE
    # verilir). Prod bunu MUTLAKA ayarlamalı; boşsa metrics_job.main() admin_database_url'e
    # düşer (dev/test kolaylığı — prod'da bu düşüş YANLIŞ role bağlanmak demektir).
    metrics_job_database_url: str = ""

    # Auth — staff Supabase projesi kiracı projesinden AYRI; aud farklı.
    admin_supabase_project_url: str = ""
    admin_supabase_jwt_aud: str = "platform-admin"
    admin_jwks_timeout_s: int = 10

    # H5 gate — varsayılan KAPALI (yasal/hukuki onay öncesi hiçbir platform-admin uç aktif olmaz).
    h5_legal_ready: bool = False

    # Impersonation okuma vekili — oturum başına kümülatif servis edilen satır tavanı (bkz. Task 9).
    impersonation_volume_cap: int = 5000

    # IP allowlist — altyapı (ör. Railway private networking) zorunlu kılar; uygulama tarafı savunma derinliği.
    admin_allowed_ips: str = ""

    # Rate-limit Redis — boş = limiter tamamen devre dışı (dev/test/Redis'siz deploy).
    admin_redis_url: str = ""
    # Salt-okuma uçları dakikalık limiti — Redis çökerse yerel-fallback ile korunur (degrade).
    admin_rate_limit_read_per_min: int = 120
    # Yazma/state-değiştiren uçlar dakikalık limiti — Redis çökerse fail-closed 503.
    admin_rate_limit_write_per_min: int = 30

    @property
    def admin_supabase_issuer(self) -> str:
        return f"{self.admin_supabase_project_url.rstrip('/')}/auth/v1"

    @property
    def admin_jwks_url(self) -> str:
        return f"{self.admin_supabase_project_url.rstrip('/')}/auth/v1/.well-known/jwks.json"


@lru_cache
def get_admin_settings() -> AdminSettings:
    return AdminSettings()
