import logging

from app.billing.pricing import COST_BUDGET_MICROS, cost_budget_for, cost_micros


def test_cost_micros_sonnet():
    # 3175*3.0 + 5890*15.0 = 9525 + 88350 = 97875 micros (~$0.098)
    assert cost_micros("claude-sonnet-4-6", 3175, 5890) == 97875


def test_cost_micros_zero_tokens():
    assert cost_micros("claude-sonnet-4-6", 0, 0) == 0


def test_cost_micros_unknown_model_returns_zero_and_warns(caplog):
    with caplog.at_level(logging.WARNING):
        assert cost_micros("gpt-4-imaginary", 1000, 1000) == 0
    assert any("gpt-4-imaginary" in r.message for r in caplog.records)


def test_cost_budget_for_known_plans():
    assert cost_budget_for("baslangic") == 2_000_000
    assert cost_budget_for("standart") == 40_000_000
    assert cost_budget_for("premium") == 150_000_000


def test_cost_budget_for_unknown_plan_is_none():
    assert cost_budget_for("altin") is None


def test_budget_table_keys_are_known_plans():
    assert set(COST_BUDGET_MICROS) == {"baslangic", "standart", "premium"}
