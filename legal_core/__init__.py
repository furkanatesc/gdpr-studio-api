"""legal_core — KVKK/GDPR grounded doküman üretiminin saf çekirdeği.

Electron prototipinin worker.py + db_retriever.py mantığı buraya, IO'dan
arındırılmış ve test edilebilir biçimde taşınmıştır. Veri erişimi (kategoriler,
iş kuralları) ve model çağrısı enjekte edilen arayüzlerle sağlanır; böylece aynı
çekirdek hem web (Postgres) hem masaüstü (SQLite/JSON) tarafında kullanılır.
"""

from .generate import generate_document
from .grounding import TAG_SYNONYMS, CategoryRepository, Grounding
from .models import (
    DocType,
    GenerateRequest,
    GenerateResponse,
    GroundingRecord,
    InventoryRecord,
    Usage,
)
from .prompt import DISCLAIMER, build_prompt, format_inventory
from .provider import ModelProvider, ProviderResult
from .rules import GLOBAL_RULES, BusinessRuleRepository

__all__ = [
    "DocType",
    "GenerateRequest",
    "GenerateResponse",
    "GroundingRecord",
    "InventoryRecord",
    "Usage",
    "Grounding",
    "CategoryRepository",
    "TAG_SYNONYMS",
    "GLOBAL_RULES",
    "BusinessRuleRepository",
    "DISCLAIMER",
    "build_prompt",
    "format_inventory",
    "ModelProvider",
    "ProviderResult",
    "generate_document",
]
