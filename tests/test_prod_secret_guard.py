"""Prod secret/config boot-guard — saf predikat tablo testi (gerçek-ölçek denetimi #2).

prod'da guard'sız kalan kritik config'leri fail-fast yakalar: default DATABASE_URL
(localhost), boş SUPABASE_PROJECT_URL, boş INTERNAL_API_TOKEN, açık AUTH_DEV_BYPASS.
"""

import pytest

from app.auth.startup_guard import prod_secret_violations, verify_prod_secrets

_DEFAULT_DB = "postgresql+psycopg://kvkk:kvkk@localhost:5432/kvkk"
_REAL_DB = "postgresql+psycopg://app:pw@db.railway.internal:5432/kvkk"


def _kw(**over):
    base = dict(
        environment="production",
        database_url=_REAL_DB,
        supabase_project_url="https://staff.supabase.co",
        internal_api_token="a-token",
        auth_dev_bypass=False,
    )
    base.update(over)
    return base


def test_clean_prod_has_no_violations():
    assert prod_secret_violations(**_kw()) == []


def test_non_prod_never_violates_even_if_all_bad():
    v = prod_secret_violations(
        **_kw(
            environment="development",
            database_url=_DEFAULT_DB,
            supabase_project_url="",
            internal_api_token="",
            auth_dev_bypass=True,
        )
    )
    assert v == []


def test_default_localhost_db_flagged():
    assert len(prod_secret_violations(**_kw(database_url=_DEFAULT_DB))) == 1


def test_empty_supabase_url_flagged():
    assert len(prod_secret_violations(**_kw(supabase_project_url=""))) == 1


def test_empty_internal_token_flagged():
    assert len(prod_secret_violations(**_kw(internal_api_token=""))) == 1


def test_auth_dev_bypass_in_prod_flagged():
    assert len(prod_secret_violations(**_kw(auth_dev_bypass=True))) == 1


def test_multiple_violations_aggregated():
    v = prod_secret_violations(
        **_kw(
            database_url=_DEFAULT_DB,
            supabase_project_url="",
            internal_api_token="",
            auth_dev_bypass=True,
        )
    )
    assert len(v) == 4


def test_verify_raises_in_prod_with_violations():
    class _S:
        environment = "production"
        database_url = _DEFAULT_DB
        supabase_project_url = ""
        internal_api_token = ""
        auth_dev_bypass = False

    with pytest.raises(RuntimeError):
        verify_prod_secrets(_S())


def test_verify_noop_when_clean():
    class _S:
        environment = "production"
        database_url = _REAL_DB
        supabase_project_url = "https://staff.supabase.co"
        internal_api_token = "a-token"
        auth_dev_bypass = False

    verify_prod_secrets(_S())  # raise etmemeli
