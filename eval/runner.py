"""Eval runner — golden set'i çalıştırır, skorlu rapor üretir, exit code döndürür.

Kullanım:
  python -m eval.runner                 # tüm senaryolar (gerçek model çağrısı; .env anahtarı gerekir)
  python -m eval.runner aydinlatma_saglik cerez_politikasi
  python -m eval.runner --grounding-only   # modelsiz, ücretsiz (yalnızca grounding doğruluğu)
"""

from __future__ import annotations

import sys
import time
import unicodedata
from collections import defaultdict

from legal_core import generate_document
from legal_core.adapters import DictBusinessRuleRepository, JsonCategoryRepository
from legal_core.grounding import Grounding
from legal_core.provider import AnthropicProvider

from app.config import get_settings
from app.seed import CATEGORIES_PATH, RULES

from .cases import GOLDEN, EvalCase, by_name
from .checks import (
    CheckResult,
    check_articles,
    check_disclaimer,
    check_retention_not_fabricated,
    check_sections,
    check_special_category,
)


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def build_grounding() -> Grounding:
    return Grounding(JsonCategoryRepository(CATEGORIES_PATH))


def build_rules_repo() -> DictBusinessRuleRepository:
    d: dict[str, list[str]] = defaultdict(list)
    for turu, metni in RULES:
        d[turu].append(metni)
    return DictBusinessRuleRepository(d)


def grounding_check(case: EvalCase, grounding: Grounding) -> CheckResult:
    resolved = {_nfc(r) for r in grounding.resolve_categories(list(case.request.veriler))}
    expected = {_nfc(e) for e in case.expected_grounding}
    missing = expected - resolved
    return CheckResult(
        "grounding",
        not missing,
        f"çözüldü: {sorted(resolved) or '∅'}"
        + (f" | EKSİK beklenen: {sorted(missing)}" if missing else ""),
    )


def model_checks(case: EvalCase, text: str) -> list[CheckResult]:
    results = [
        check_articles(text, case.articles) if case.articles else CheckResult("madde_atıfları", True, "n/a"),
        check_sections(text, case.sections),
        check_disclaimer(text),
    ]
    if case.special_category:
        results.append(check_special_category(text))
    if case.retention_placeholder:
        results.append(check_retention_not_fabricated(text))
    return results


def run_case(case: EvalCase, grounding, rules_repo, provider) -> tuple[list[CheckResult], dict]:
    checks = [grounding_check(case, grounding)]
    meta: dict = {}
    if provider is not None:
        t = time.time()
        res = generate_document(case.request, grounding=grounding, rules_repo=rules_repo, provider=provider)
        meta = {
            "saniye": round(time.time() - t),
            "in": res.usage.input_tokens if res.usage else 0,
            "out": res.usage.output_tokens if res.usage else 0,
        }
        checks += model_checks(case, res.text)
    return checks, meta


def main(argv: list[str]) -> int:
    grounding_only = "--grounding-only" in argv
    names = [a for a in argv if not a.startswith("--")]
    cases = [by_name(n) for n in names] if names else GOLDEN

    grounding = build_grounding()
    rules_repo = build_rules_repo()

    provider = None
    if not grounding_only:
        key = get_settings().managed_anthropic_api_key
        if not key:
            print("HATA: MANAGED_ANTHROPIC_API_KEY yok (.env). Modelsiz için --grounding-only kullanın.")
            return 2
        provider = AnthropicProvider(key, model=get_settings().default_model)
        print(f"Mod: GERÇEK MODEL ({get_settings().default_model}) — {len(cases)} senaryo, çağrı başına ~60-100s.\n")
    else:
        print(f"Mod: yalnızca grounding (modelsiz) — {len(cases)} senaryo.\n")

    total = passed = 0
    failed_cases: list[str] = []

    for case in cases:
        results, meta = run_case(case, grounding, rules_repo, provider)
        ok = sum(1 for r in results if r.passed)
        total += len(results)
        passed += ok
        head = f"=== {case.name} ==="
        if meta:
            head += f"  ({meta['saniye']}s · in {meta['in']} / out {meta['out']})"
        print(head)
        for r in results:
            mark = "PASS" if r.passed else "FAIL"
            print(f"  [{mark}] {r.name}: {r.detail}")
        if ok < len(results):
            failed_cases.append(case.name)
        print(f"  -> {ok}/{len(results)}\n")

    print("=" * 50)
    print(f"TOPLAM: {passed}/{total} kontrol geçti.")
    if failed_cases:
        print(f"BAŞARISIZ senaryolar: {failed_cases}")
        return 1
    print("Tüm hukuki-doğruluk kontrolleri GEÇTİ.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
