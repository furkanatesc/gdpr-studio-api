"""Uyum kontrol listesi + skor uçları.

GET /api/compliance/checklist  → gruplu gereksinim listesi + genel/grup skoru (org RLS).
PUT /api/compliance/status/{key} → durum upsert (source=user); rol: yonetici VEYA avukat.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from legal_core.models import _CamelModel

from ..auth.identity import Identity, get_current_identity
from ..auth.tenant_session import tenant_session
from ..repositories import ComplianceRepository, GeneratedDocumentRepository
from .compliance_logic import compute_score, evaluate_auto_signal

router = APIRouter(prefix="/api/compliance", tags=["compliance"])

# Durum yazımı ortak uyum işi → yonetici + avukat. (require_role tek rol; burada ikili guard.)
_EDIT_ROLES = {"yonetici", "avukat"}


def _require_compliance_editor(identity: Identity = Depends(get_current_identity)) -> Identity:
    if identity.role not in _EDIT_ROLES:
        raise HTTPException(status_code=403, detail="Bu işlem için yetkiniz yok.")
    return identity


class ChecklistItem(_CamelModel):
    key: str
    title: str
    madde_ref: str
    description: str
    source_type: str
    status: str | None = None
    source: str | None = None
    note: str | None = None
    suggestion: str | None = None


class ChecklistGroup(_CamelModel):
    group: str
    items: list[ChecklistItem]


class ChecklistOut(_CamelModel):
    groups: list[ChecklistGroup]
    score: float | None
    group_scores: dict[str, float | None]


class StatusUpdate(BaseModel):
    # Tanımsız (çöp) alan sessizce yutulmaz → 422.
    model_config = ConfigDict(extra="forbid")

    status: Literal["yapildi", "eksik", "uygulanmaz"]
    note: str | None = None


def _build_item(req, status_row, doc_types: set[str]) -> ChecklistItem:
    # auto kalem + saklı status yoksa → canlı öneri (skora sayılmaz, UI onaylatır).
    suggestion = None
    if status_row is None and req.source_type == "auto":
        suggestion = evaluate_auto_signal(req.auto_signal or "", doc_types)
    return ChecklistItem(
        key=req.key,
        title=req.title,
        madde_ref=req.madde_ref,
        description=req.description,
        source_type=req.source_type,
        status=status_row.status if status_row else None,
        source=status_row.source if status_row else None,
        note=status_row.note if status_row else None,
        suggestion=suggestion,
    )


@router.get("/checklist", response_model=ChecklistOut)
def get_checklist(
    identity: Identity = Depends(get_current_identity),
    session: Session = Depends(tenant_session),
) -> ChecklistOut:
    repo = ComplianceRepository(session)
    reqs = repo.all_requirements()
    statuses = repo.statuses_for_org(identity.org_id)
    doc_types = GeneratedDocumentRepository(session).doc_types_for_org(identity.org_id)

    groups: dict[str, list[ChecklistItem]] = {}
    group_order: list[str] = []
    tot = {"total": 0, "yapildi": 0, "uygulanmaz": 0}
    per_group: dict[str, dict[str, int]] = {}
    for req in reqs:
        status_row = statuses.get(req.key)
        item = _build_item(req, status_row, doc_types)
        if req.group not in groups:
            groups[req.group] = []
            group_order.append(req.group)
            per_group[req.group] = {"total": 0, "yapildi": 0, "uygulanmaz": 0}
        groups[req.group].append(item)
        tot["total"] += 1
        per_group[req.group]["total"] += 1
        if status_row is not None and status_row.status in ("yapildi", "uygulanmaz"):
            tot[status_row.status] += 1
            per_group[req.group][status_row.status] += 1

    score = compute_score(tot["yapildi"], tot["total"], tot["uygulanmaz"])
    group_scores = {
        g: compute_score(c["yapildi"], c["total"], c["uygulanmaz"]) for g, c in per_group.items()
    }
    return ChecklistOut(
        groups=[ChecklistGroup(group=g, items=groups[g]) for g in group_order],
        score=score,
        group_scores=group_scores,
    )


@router.put("/status/{key}", response_model=ChecklistItem)
def put_status(
    key: str,
    body: StatusUpdate,
    identity: Identity = Depends(_require_compliance_editor),
    session: Session = Depends(tenant_session),
) -> ChecklistItem:
    repo = ComplianceRepository(session)
    req_by_key = {r.key: r for r in repo.all_requirements()}
    req = req_by_key.get(key)
    if req is None:
        raise HTTPException(status_code=404, detail="Gereksinim bulunamadı.")
    row = repo.upsert_status(identity.org_id, key, body.status, "user", body.note, identity.user_id)
    session.commit()  # durability: get_session commit etmez → uç kendi işlemini kapatır
    doc_types = GeneratedDocumentRepository(session).doc_types_for_org(identity.org_id)
    return _build_item(req, row, doc_types)
