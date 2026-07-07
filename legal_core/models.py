"""API sözleşmesi + iç veri modelleri.

Wire modelleri (GenerateRequest/Response, GroundingRecord) web/lib/types.ts ile
BİREBİR uyumludur — JSON'da camelCase (veriTurleri, hukukiSebepler, ...).
Pydantic alias generator ile snake_case alanlar camelCase'e serileşir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class DocType(str, Enum):
    aydinlatma = "aydinlatma"
    cerez = "cerez"
    kayit = "kayit"
    dpa = "dpa"
    dpia = "dpia"
    ihlal = "ihlal"


class _CamelModel(BaseModel):
    """camelCase JSON ↔ snake_case Python; her iki adla da doldurulabilir."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class GroundingRecord(_CamelModel):
    """Şeffaflık kaydı — çıktının dayandığı envanter kategorisi (web kontratı)."""

    kategori: str
    veri_turleri: list[str] = []
    amaclar: list[str] = []
    hukuki_sebepler: list[str] = []
    kisi_gruplari: list[str] = []
    saklama_sureleri: list[str] = []


class GenerateRequest(_CamelModel):
    # İstek gövdesi istemciden gelir — tanımsız (çöp) alan sessizce yutulmaz, 422 döner.
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")

    type: DocType
    fields: dict[str, str] = {}
    veriler: list[str] = []
    amaclar: list[str] = []


class Usage(_CamelModel):
    input_tokens: int
    output_tokens: int


class GenerateResponse(_CamelModel):
    text: str
    grounding: list[GroundingRecord] = []
    model: str
    disclaimer: str
    usage: Usage | None = None


class ApiError(_CamelModel):
    error: str
    details: str | None = None


@dataclass(frozen=True)
class InventoryRecord:
    """Tam envanter kaydı (iç kullanım — prompt'a enjekte edilir).

    GroundingRecord'un üst kümesidir; tedbir alanlarını da taşır (prompt'ta
    gerekebilir). API yanıtındaki grounding bu kaydın bir alt kümesidir.
    """

    kategori: str
    veri_turleri: list[str] = field(default_factory=list)
    amaclar: list[str] = field(default_factory=list)
    hukuki_sebepler: list[str] = field(default_factory=list)
    kisi_gruplari: list[str] = field(default_factory=list)
    saklama_sureleri: list[str] = field(default_factory=list)
    idari_tedbirler: list[str] = field(default_factory=list)
    teknik_tedbirler: list[str] = field(default_factory=list)

    def to_grounding(self) -> GroundingRecord:
        return GroundingRecord(
            kategori=self.kategori,
            veri_turleri=self.veri_turleri,
            amaclar=self.amaclar,
            hukuki_sebepler=self.hukuki_sebepler,
            kisi_gruplari=self.kisi_gruplari,
            saklama_sureleri=self.saklama_sureleri,
        )
