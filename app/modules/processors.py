"""Veri işleyen (client_processors) CRUD + envanter aktarım adları — DPA üretimi için."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from sqlalchemy.orm import Session

from legal_core.dpa_scope import distinct_aktarim_adlari

from ..auth.identity import Identity, get_current_identity
from ..auth.tenant_session import tenant_session
from ..repositories import ClientProcessorRepository, ClientRepository, PostgresProcessRepository

router = APIRouter(prefix="/api/clients", tags=["processors"])


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class ProcessorIn(_Camel):
    ad: str
    unvan: str
    adres: str | None = None
    yetkili_kisi: str | None = None
    iletisim: str | None = None
    vergi_dairesi_no: str | None = None
    yurt_disi: bool = False
    alt_isleyen_var: bool = False
    aktarim_aliases: list[str] = []
    notlar: str | None = None


class ProcessorOut(_Camel):
    id: uuid.UUID
    ad: str
    unvan: str
    adres: str | None
    yetkili_kisi: str | None
    iletisim: str | None
    vergi_dairesi_no: str | None
    yurt_disi: bool
    alt_isleyen_var: bool
    aktarim_aliases: list[str]
    notlar: str | None


class AktarimAdlariOut(_Camel):
    adlar: list[str]


def _require_client(session: Session, org_id, client_id):
    if ClientRepository(session).get(org_id, client_id) is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")


def _out(row) -> ProcessorOut:
    return ProcessorOut(
        id=row.id, ad=row.ad, unvan=row.unvan, adres=row.adres,
        yetkili_kisi=row.yetkili_kisi, iletisim=row.iletisim,
        vergi_dairesi_no=row.vergi_dairesi_no, yurt_disi=row.yurt_disi,
        alt_isleyen_var=row.alt_isleyen_var, aktarim_aliases=list(row.aktarim_aliases or []),
        notlar=row.notlar,
    )


@router.get("/{client_id}/processors", response_model=list[ProcessorOut], response_model_by_alias=True)
def list_processors(client_id: uuid.UUID, identity: Identity = Depends(get_current_identity),
                    session: Session = Depends(tenant_session)):
    _require_client(session, identity.org_id, client_id)
    return [_out(r) for r in ClientProcessorRepository(session).list(identity.org_id, client_id)]


@router.post("/{client_id}/processors", response_model=ProcessorOut,
             response_model_by_alias=True, status_code=201)
def create_processor(client_id: uuid.UUID, body: ProcessorIn,
                     identity: Identity = Depends(get_current_identity),
                     session: Session = Depends(tenant_session)):
    _require_client(session, identity.org_id, client_id)
    row = ClientProcessorRepository(session).create(
        identity.org_id, client_id, **body.model_dump())
    session.commit()
    return _out(row)


@router.get("/{client_id}/processors/{processor_id}", response_model=ProcessorOut, response_model_by_alias=True)
def get_processor(client_id: uuid.UUID, processor_id: uuid.UUID,
                  identity: Identity = Depends(get_current_identity),
                  session: Session = Depends(tenant_session)):
    _require_client(session, identity.org_id, client_id)
    row = ClientProcessorRepository(session).get(identity.org_id, client_id, processor_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Veri işleyen bulunamadı.")
    return _out(row)


@router.put("/{client_id}/processors/{processor_id}", response_model=ProcessorOut,
            response_model_by_alias=True)
def update_processor(client_id: uuid.UUID, processor_id: uuid.UUID, body: ProcessorIn,
                     identity: Identity = Depends(get_current_identity),
                     session: Session = Depends(tenant_session)):
    _require_client(session, identity.org_id, client_id)
    row = ClientProcessorRepository(session).update(
        identity.org_id, client_id, processor_id, **body.model_dump())
    if row is None:
        raise HTTPException(status_code=404, detail="Veri işleyen bulunamadı.")
    session.commit()
    return _out(row)


@router.delete("/{client_id}/processors/{processor_id}", status_code=204)
def delete_processor(client_id: uuid.UUID, processor_id: uuid.UUID,
                     identity: Identity = Depends(get_current_identity),
                     session: Session = Depends(tenant_session)):
    _require_client(session, identity.org_id, client_id)
    if not ClientProcessorRepository(session).delete(identity.org_id, client_id, processor_id):
        raise HTTPException(status_code=404, detail="Veri işleyen bulunamadı.")
    session.commit()
    return Response(status_code=204)


@router.get("/{client_id}/aktarim-adlari", response_model=AktarimAdlariOut, response_model_by_alias=True)
def aktarim_adlari(client_id: uuid.UUID, identity: Identity = Depends(get_current_identity),
                   session: Session = Depends(tenant_session)):
    _require_client(session, identity.org_id, client_id)
    records = PostgresProcessRepository(session).client_processes(client_id)
    return AktarimAdlariOut(adlar=distinct_aktarim_adlari(records))
