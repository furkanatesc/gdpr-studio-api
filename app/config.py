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

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
