"""Supabase Admin API — auth kaydı silme (DSAR purge). Env-gated + best-effort.

SUPABASE_SERVICE_ROLE_KEY yoksa (dev/test) atlanır + log. Hata purge'i bloke etmez.
"""

from __future__ import annotations

import logging

import httpx

from .config import get_settings

_log = logging.getLogger("app.dsar")


def delete_supabase_user(supabase_user_id: str) -> bool:
    """Supabase auth kaydını sil. Başarı/atlama → True; kalıcı hata → False (loglar)."""
    s = get_settings()
    if not s.supabase_service_role_key or not s.supabase_project_url:
        _log.info("supabase service_role anahtarı yok → auth silme atlandı (user=%s)", supabase_user_id)
        return False
    url = f"{s.supabase_project_url.rstrip('/')}/auth/v1/admin/users/{supabase_user_id}"
    headers = {
        "Authorization": f"Bearer {s.supabase_service_role_key}",
        "apikey": s.supabase_service_role_key,
    }
    try:
        r = httpx.delete(url, headers=headers, timeout=15)
    except Exception:
        _log.exception("supabase auth silme isteği başarısız (user=%s)", supabase_user_id)
        return False
    if r.status_code in (200, 204, 404):  # 404 = zaten yok
        return True
    _log.warning(
        "supabase auth silme beklenmeyen durum %s (user=%s)", r.status_code, supabase_user_id
    )
    return False
