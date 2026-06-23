"""Auth modülü — Tenant dikişi artık gerçek kimlikten (org) türetilir."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends

from ..auth.identity import Identity, get_current_identity


@dataclass(frozen=True)
class Tenant:
    id: str
    name: str


def get_current_tenant(identity: Identity = Depends(get_current_identity)) -> Tenant:
    return Tenant(id=str(identity.org_id), name="")
