"""Süreç şablonu uçları — sihirbazın kişi grubu adımını besler."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth.identity import Identity, get_current_identity
from ..auth.tenant_session import tenant_session
from ..models import Organization
from ..repositories import PostgresProcessRepository

router = APIRouter(prefix="/api/processes", tags=["processes"])


@router.get("/person-groups", response_model=list[str])
def person_groups(
    session: Session = Depends(tenant_session),
    identity: Identity = Depends(get_current_identity),
) -> list[str]:
    """Org'un sektöründeki kişi grupları. Sektör yoksa boş liste (sahte seçenek üretilmez)."""
    org = session.get(Organization, identity.org_id)
    if org is None or not org.sector:
        return []
    return PostgresProcessRepository(session).person_groups(org.sector)
