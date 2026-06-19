"""Üretim orkestrasyonu — grounding + kurallar + prompt + model çağrısı.

Tek genel akış: etiketleri çöz → envanter kayıtlarını getir → global + türe özel
kuralları topla → prompt kur → model çağır → disclaimer'ı garanti et → yanıt kur.
Tüm IO bağımlılıkları (grounding repo, kural repo, model provider) enjekte edilir.
"""

from __future__ import annotations

from .grounding import Grounding
from .models import GenerateRequest, GenerateResponse, Usage
from .prompt import DISCLAIMER, build_prompt, ensure_disclaimer
from .provider import DEFAULT_MAX_TOKENS, ModelProvider
from .rules import GLOBAL_RULES, BusinessRuleRepository


def generate_document(
    request: GenerateRequest,
    *,
    grounding: Grounding,
    rules_repo: BusinessRuleRepository,
    provider: ModelProvider,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> GenerateResponse:
    doc_type = request.type.value

    # Etiket kaynağı: web kontratında çerez/risk kategorileri de 'veriler' altında gelir.
    tags = list(request.veriler)

    inventory = grounding.inventory_rules(tags)
    rules = GLOBAL_RULES + rules_repo.business_rules(doc_type)

    # Kullanıcı girdisini prompt'a olduğu gibi (tip + alanlar + etiketler) ver.
    user_input = {
        "type": doc_type,
        "fields": request.fields,
        "veriler": request.veriler,
        "amaclar": request.amaclar,
    }
    prompt = build_prompt(doc_type, user_input, inventory, rules)

    result = provider.generate(prompt, max_tokens=max_tokens)
    text = ensure_disclaimer(result.text)

    return GenerateResponse(
        text=text,
        grounding=[r.to_grounding() for r in inventory],
        model=result.model,
        disclaimer=DISCLAIMER,
        usage=Usage(input_tokens=result.input_tokens, output_tokens=result.output_tokens),
    )
