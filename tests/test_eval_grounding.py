"""Golden set'in deterministik (modelsiz) kısmı — grounding doğruluğu.

Ücretsiz/hızlı; CI'da koşar. Model çağrılı kontroller `python -m eval.runner` ile ayrı.
"""

import pytest

from eval.cases import GOLDEN
from eval.runner import build_grounding, grounding_check


@pytest.mark.parametrize("case", GOLDEN, ids=lambda c: c.name)
def test_grounding_golden(case):
    g = build_grounding()
    r = grounding_check(case, g)
    assert r.passed, f"{case.name}: {r.detail}"
