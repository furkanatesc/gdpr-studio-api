"""Uygulama ayarları (ortam değişkenlerinden)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # Veritabanı / altyapı
    database_url: str = "postgresql+psycopg://kvkk:kvkk@localhost:5432/kvkk"
    redis_url: str = "redis://localhost:6379/0"

    # Managed mod sunucu anahtarı (web). Boşsa yalnızca BYOK çalışır.
    managed_anthropic_api_key: str = ""
    default_model: str = "claude-sonnet-4-6"
    max_tokens: int = 8000

    # CORS — web frontend kaynakları (virgülle ayrılmış)
    allowed_origins: str = "http://localhost:3000"

    environment: str = "development"

    # Gözlemlenebilirlik
    log_level: str = "INFO"
    sentry_dsn: str = ""  # boşsa Sentry devre dışı (no-op)

    # Redis (opsiyonel — erişilemezse rate-limit fail-open, cache miss)
    rate_limit_generate_per_min: int = 10  # tenant başına dakikalık üretim isteği tavanı
    categories_cache_ttl_s: int = 300  # /api/categories cache süresi

    # --- Auth (Supabase yalnız-IdP) ---
    supabase_project_url: str = ""  # boşsa + dev → dev bypass devreye girer
    supabase_jwt_aud: str = "authenticated"
    auth_dev_bypass: bool = False  # True → JWT doğrulamadan dev kimliği

    # --- Davet ---
    invite_secret: str = "dev-invite-secret-change-me"  # itsdangerous imza anahtarı
    invite_ttl_hours: int = 72

    # --- E-posta (env-gated; sağlayıcısız 'log') ---
    email_provider: str = "log"  # 'log' | 'resend'
    resend_api_key: str = ""
    email_from: str = "KVKK Yönetim <noreply@kvkkyonetim.com>"

    # Frontend taban URL (davet linki üretimi)
    app_base_url: str = "http://localhost:3000"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def supabase_jwks_url(self) -> str:
        base = self.supabase_project_url.rstrip("/")
        return f"{base}/auth/v1/.well-known/jwks.json" if base else ""


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
