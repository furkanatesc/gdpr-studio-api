"""Uygulama ayarları (ortam değişkenlerinden)."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from .semantic_config import DEFAULT_SEMANTIC_MODEL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="", extra="ignore")

    # Veritabanı / altyapı
    database_url: str = "postgresql+psycopg://kvkk:kvkk@localhost:5432/kvkk"
    redis_url: str = "redis://localhost:6379/0"

    # Managed mod sunucu anahtarı (web). Boşsa yalnızca BYOK çalışır.
    managed_anthropic_api_key: str = ""
    default_model: str = "claude-sonnet-4-6"
    max_tokens: int = 8000
    # Süreç grounding'i prompt'a kaç süreç bassın (0 = sınırsız). Kırpma sessiz değildir.
    process_cap: int = 60
    # Sağlayıcı dayanıklılığı: sync üretim uçları threadpool'da; timeout/retry olmadan
    # upstream asılırsa worker+DB bağlantısı süresiz tutulur (H1-4).
    anthropic_timeout_s: float = 60.0
    anthropic_max_retries: int = 2

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

    # --- Stripe faturalandırma (env-gated: STRIPE_SECRET_KEY boşsa billing kapalı) ---
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_standart_month: str = ""
    stripe_price_standart_year: str = ""
    stripe_price_premium_month: str = ""
    stripe_price_premium_year: str = ""
    billing_success_url: str = "http://localhost:3000/app/faturalama?billing=success"
    billing_cancel_url: str = "http://localhost:3000/app/faturalama?billing=cancel"

    # --- Semantik fallback (env-gated: kapalıyken no-op, model yüklenmez) ---
    semantic_fallback_enabled: bool = False
    semantic_model: str = DEFAULT_SEMANTIC_MODEL
    semantic_threshold: float = 0.80  # cosine benzerlik tabanı; altı → eşleşme yok

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def supabase_jwks_url(self) -> str:
        base = self.supabase_project_url.rstrip("/")
        return f"{base}/auth/v1/.well-known/jwks.json" if base else ""

    @property
    def billing_enabled(self) -> bool:
        return bool(self.stripe_secret_key)

    @property
    def price_map(self) -> dict[str, tuple[str, str]]:
        raw = {
            self.stripe_price_standart_month: ("standart", "month"),
            self.stripe_price_standart_year: ("standart", "year"),
            self.stripe_price_premium_month: ("premium", "month"),
            self.stripe_price_premium_year: ("premium", "year"),
        }
        return {pid: v for pid, v in raw.items() if pid}

    def price_for(self, plan: str, interval: str) -> str | None:
        for pid, (p, i) in self.price_map.items():
            if p == plan and i == interval:
                return pid
        return None


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
