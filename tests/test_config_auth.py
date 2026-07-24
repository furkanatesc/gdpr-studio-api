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


def test_max_tokens_for_kayit_ozel_tavan_kullanir():
    """VERBIS kaydi surec basina 8 sutunluk blok gerektirir; uzunluk envanterle dogrusal
    buyur -> 8000 200+ surecli envanterlerde yetmez. Yalniz 'kayit' 32000 kullanmali."""
    s = Settings(_env_file=None)
    assert s.max_tokens == 8000
    assert s.max_tokens_envanter_belgesi == 32000
    assert s.max_tokens_for("aydinlatma") == 32000
    assert s.max_tokens_for("kayit") == 32000


def test_max_tokens_for_sabit_boyutlu_turler_degismez():
    """Yuksek tavan yalniz envanterden tureyen turler icin; sabit boyutlu turler 8000'de kalir."""
    s = Settings(_env_file=None)
    for doc_type in ("cerez", "dpa", "dpia", "ihlal"):
        assert s.max_tokens_for(doc_type) == 8000
