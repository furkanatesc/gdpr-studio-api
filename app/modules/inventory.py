# app/modules/inventory.py
"""Şablon indir + grounding combobox seçenekleri."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import Response

from ..auth.identity import Identity, get_current_identity
from ..grounding_options import grounding_options
from ..inventory_template import build_template_xlsx
from ..workbook_template import build_workbook_template_xlsx

router = APIRouter(prefix="/api", tags=["inventory"])


@router.get("/inventory/template")
def template() -> Response:
    return Response(content=build_template_xlsx(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="kvkk-envanter-sablonu.xlsx"'})


@router.get("/inventory/workbook-template")
def workbook_template() -> Response:
    return Response(content=build_workbook_template_xlsx(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="kvkk-anket-kitabi.xlsx"'})


@router.get("/grounding/options")
def options(_: Identity = Depends(get_current_identity)) -> dict:
    return grounding_options()
