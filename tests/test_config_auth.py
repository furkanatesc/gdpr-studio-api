from app.config import Settings


def test_auth_defaults_dev_bypass_off_and_jwks_derived():
    s = Settings(_env_file=None, supabase_project_url="https://abc.supabase.co")
    assert s.auth_dev_bypass is False
    assert s.supabase_jwt_aud == "authenticated"
    assert s.supabase_jwks_url == "https://abc.supabase.co/auth/v1/.well-known/jwks.json"


def test_invite_and_email_defaults():
    s = Settings(_env_file=None)
    assert s.invite_ttl_hours == 72
    assert s.email_provider == "log"  # sağlayıcısız varsayılan
    assert s.app_base_url  # boş değil
