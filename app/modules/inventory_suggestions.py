"""Envanter bos alanlari icin grounding onerileri (salt-okunur)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from legal_core.canonical import load_canonicalizer
from legal_core.inventory_enrich import enrich_inventory
from legal_core.scoring import kayit_completeness_score

from ..auth.identity import Identity, get_current_identity
from ..auth.tenant_session import tenant_session
from ..repositories import ClientRepository, PostgresProcessRepository

router = APIRouter(prefix="/api/clients", tags=["inventory"])

_CANON = load_canonicalizer()


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class InventorySuggestionRowOut(_Camel):
    index: int
    departman: str
    is_sureci: str
    alt_surec: str
    kisi_grubu: str
    oneriler: dict[str, list[str]]
    elle_alanlar: list[str]


class InventorySuggestionsOut(_Camel):
    bos_slot: int
    tamlik: float | None
    rows: list[InventorySuggestionRowOut]


def _bos_slot(records) -> int:
    n = 0
    for r in records:
        n += not r.kisi_grubu
        n += not (r.kategoriler or r.veri_turleri)
        n += not r.amaclar
        n += not r.hukuki_sebepler
        n += not r.saklama_sureleri
        n += not r.aktarim
    return n


@router.get("/{client_id}/inventory/suggestions", response_model=InventorySuggestionsOut)
def inventory_suggestions(client_id: uuid.UUID,
                          identity: Identity = Depends(get_current_identity),
                          session: Session = Depends(tenant_session)) -> InventorySuggestionsOut:
    client = ClientRepository(session).get(identity.org_id, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")
    repo = PostgresProcessRepository(session)
    records = repo.client_processes(client_id)
    suggestions = enrich_inventory(records, client.sector or "sirket", repo, canonicalizer=_CANON)
    rows = [
        InventorySuggestionRowOut(
            index=s.index, departman=s.departman, is_sureci=s.is_sureci,
            alt_surec=s.alt_surec, kisi_grubu=s.kisi_grubu,
            oneriler=s.oneriler, elle_alanlar=s.elle_alanlar,
        )
        for s in suggestions
    ]
    return InventorySuggestionsOut(
        bos_slot=_bos_slot(records),
        tamlik=kayit_completeness_score(records),
        rows=rows,
    )
