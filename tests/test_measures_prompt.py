from legal_core.adapters import DictCategoryRepository, DictMeasureRepository
from legal_core.grounding import Grounding
from legal_core.prompt import build_prompt, format_measures

_M = ["Ağ güvenliği sağlanır", "Erişim yetkileri sınırlandırılır"]


def test_format_measures_lists_all():
    out = format_measures(_M)
    assert "Ağ güvenliği sağlanır" in out and "Erişim yetkileri sınırlandırılır" in out


def test_format_measures_empty_is_empty_string():
    assert format_measures([]) == ""


def test_build_prompt_includes_measures_for_kayit():
    p = build_prompt("kayit", {"type": "kayit"}, [], ["kural"], measures=_M)
    assert "TEDBİR" in p.upper()
    assert "Ağ güvenliği sağlanır" in p


def test_build_prompt_omits_measures_for_aydinlatma():
    """Token: tedbir bloğu yalnız kayit/dpia/ihlal'de."""
    p = build_prompt("aydinlatma", {"type": "aydinlatma"}, [], ["kural"], measures=_M)
    assert "Ağ güvenliği sağlanır" not in p


def test_build_prompt_without_measures_unchanged():
    p = build_prompt("kayit", {"type": "kayit"}, [], ["kural"])
    assert "Ağ güvenliği sağlanır" not in p


def test_build_prompt_char_identical_when_measures_suppressed():
    """Regresyon: tedbir bloğu bastırıldığında prompt karakter-özdeş (fazladan boş satır yok)."""
    base = build_prompt("aydinlatma", {"type": "aydinlatma"}, [], ["kural"])
    with_m = build_prompt("aydinlatma", {"type": "aydinlatma"}, [], ["kural"], measures=_M)
    assert with_m == base
    assert build_prompt("kayit", {"type": "kayit"}, [], ["kural"], measures=None) == build_prompt(
        "kayit", {"type": "kayit"}, [], ["kural"], measures=[]
    )


def test_grounding_measures_empty_without_repo():
    assert Grounding(DictCategoryRepository({})).measures() == []
    g = Grounding(DictCategoryRepository({}), measure_repo=DictMeasureRepository(_M))
    assert g.measures() == _M
