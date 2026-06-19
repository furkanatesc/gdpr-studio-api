"""Auth modülü — Faz 1'de DİKİŞ (seam), gerçek auth Faz 2.

Şimdilik sabit dev tenant döner; Faz 2'de buraya gerçek sağlayıcı (Authentik/
Keycloak/Supabase EU) + RLS tenant çözümü takılır. Uçlar baştan tenant-farkındadır.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tenant:
    id: str
    name: str


def get_current_tenant() -> Tenant:
    # TODO(Faz 2): token doğrula → tenant + rol çöz (RLS).
    return Tenant(id="dev", name="Geliştirme Kiracısı")
