# app/modules/clients.py
"""Müvekkil uçları — CRUD + envanter yükleme/özet."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ..auth.identity import Identity, get_current_identity, require_role
from ..auth.tenant_session import tenant_session
from ..inventory_import import InventoryImportError, parse_inventory_xlsx
from ..repositories import ClientRepository, PostgresProcessRepository

router = APIRouter(prefix="/api/clients", tags=["clients"])


class ClientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=2, max_length=255)
    sector: str | None = None


class ClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    sector: str | None = None
    legal_name: str | None = None
    mersis: str | None = None
    vergi_dairesi: str | None = None
    vergi_no: str | None = None
    kep: str | None = None
    adres: str | None = None
    eposta: str | None = None
    telefon: str | None = None


class ClientProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str | None = None
    sector: str | None = None
    legal_name: str | None = None
    mersis: str | None = None
    vergi_dairesi: str | None = None
    vergi_no: str | None = None
    kep: str | None = None
    adres: str | None = None
    eposta: str | None = None
    telefon: str | None = None


_LIST_FIELDS = ("kategoriler", "veri_turleri", "amaclar", "hukuki_sebepler", "dayanaklar",
                "saklama_sureleri", "islem", "ortam_format", "konum",
                "idari_tedbirler", "teknik_tedbirler", "aktarim", "toplama")


class InventoryRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    departman: str = ""
    is_sureci: str = ""
    alt_surec: str = ""
    kisi_grubu: str = Field(min_length=1, max_length=255)
    kategoriler: list[str] = Field(default_factory=list)
    veri_turleri: list[str] = Field(default_factory=list)
    amaclar: list[str] = Field(default_factory=list)
    hukuki_sebepler: list[str] = Field(default_factory=list)
    dayanaklar: list[str] = Field(default_factory=list)
    saklama_sureleri: list[str] = Field(default_factory=list)
    islem: list[str] = Field(default_factory=list)
    ortam_format: list[str] = Field(default_factory=list)
    konum: list[str] = Field(default_factory=list)
    idari_tedbirler: list[str] = Field(default_factory=list)
    teknik_tedbirler: list[str] = Field(default_factory=list)
    aktarim: list[str] = Field(default_factory=list)
    toplama: list[str] = Field(default_factory=list)


class InventoryReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[InventoryRow]


def _summary(recs) -> dict:
    return {"count": len(recs), "kisiGruplari": sorted({r.kisi_grubu for r in recs}),
            "departmanlar": sorted({r.departman for r in recs if r.departman})}


def _record_to_row(r) -> dict:
    row = {"departman": r.departman, "is_sureci": r.is_sureci,
           "alt_surec": r.alt_surec, "kisi_grubu": r.kisi_grubu}
    for f in _LIST_FIELDS:
        row[f] = list(getattr(r, f))
    return row


def _row_to_replace_dict(row: InventoryRow, sector: str) -> dict:
    return {"sector": sector, "kisi_grubu": row.kisi_grubu, "departman": row.departman,
            "is_sureci": row.is_sureci, "alt_surec": row.alt_surec,
            "data": {f: getattr(row, f) for f in _LIST_FIELDS}}


@router.post("", response_model=ClientOut)
def create_client(body: ClientCreate, identity: Identity = Depends(get_current_identity),
                  session: Session = Depends(tenant_session)) -> ClientOut:
    c = ClientRepository(session).create(identity.org_id, body.name, body.sector)
    session.commit()
    return ClientOut.model_validate(c)


@router.get("", response_model=list[ClientOut])
def list_clients(identity: Identity = Depends(get_current_identity),
                 session: Session = Depends(tenant_session)) -> list[ClientOut]:
    return [ClientOut.model_validate(c) for c in ClientRepository(session).list(identity.org_id)]


@router.get("/{client_id}", response_model=ClientOut)
def get_client(client_id: uuid.UUID, identity: Identity = Depends(get_current_identity),
               session: Session = Depends(tenant_session)) -> ClientOut:
    c = ClientRepository(session).get(identity.org_id, client_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")
    return ClientOut.model_validate(c)


@router.patch("/{client_id}", response_model=ClientOut)
def update_client(client_id: uuid.UUID, body: ClientProfileUpdate,
                  identity: Identity = Depends(require_role("yonetici")),
                  session: Session = Depends(tenant_session)) -> ClientOut:
    # exclude_unset: gönderilmeyen alan korunur, açıkça null gönderilen alan temizlenir (PATCH semantiği).
    c = ClientRepository(session).update_profile(identity.org_id, client_id, **body.model_dump(exclude_unset=True))
    if c is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")
    session.commit()
    return ClientOut.model_validate(c)


@router.post("/{client_id}/inventory/import")
async def import_inventory(client_id: uuid.UUID, file: UploadFile,
                           identity: Identity = Depends(get_current_identity),
                           session: Session = Depends(tenant_session)) -> dict:
    client = ClientRepository(session).get(identity.org_id, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")
    try:
        rows = parse_inventory_xlsx(await file.read(), sector=client.sector or "sirket")
    except InventoryImportError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    repo = PostgresProcessRepository(session)
    repo.replace_client(identity.org_id, client_id, rows)
    # Özet commit'ten ÖNCE okunmalı: app.current_org_id transaction-local, commit'te sıfırlanır
    # ve RLS satırları gizler → "başarılı ama 0 kayıt".
    summary = _summary(repo.client_processes(client_id))
    session.commit()
    return summary


@router.get("/{client_id}/inventory/summary")
def inventory_summary(client_id: uuid.UUID, identity: Identity = Depends(get_current_identity),
                      session: Session = Depends(tenant_session)) -> dict:
    if ClientRepository(session).get(identity.org_id, client_id) is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")
    return _summary(PostgresProcessRepository(session).client_processes(client_id))


@router.get("/{client_id}/inventory")
def get_inventory(client_id: uuid.UUID, identity: Identity = Depends(get_current_identity),
                  session: Session = Depends(tenant_session)) -> dict:
    if ClientRepository(session).get(identity.org_id, client_id) is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")
    recs = PostgresProcessRepository(session).client_processes(client_id)
    return {"rows": [_record_to_row(r) for r in recs]}


@router.put("/{client_id}/inventory")
def replace_inventory(client_id: uuid.UUID, body: InventoryReplace,
                      identity: Identity = Depends(get_current_identity),
                      session: Session = Depends(tenant_session)) -> dict:
    client = ClientRepository(session).get(identity.org_id, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Müvekkil bulunamadı.")
    sector = client.sector or "sirket"
    rows = [_row_to_replace_dict(r, sector) for r in body.rows]
    repo = PostgresProcessRepository(session)
    repo.replace_client(identity.org_id, client_id, rows)
    summary = _summary(repo.client_processes(client_id))
    session.commit()
    return summary
