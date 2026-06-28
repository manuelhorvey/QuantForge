import threading

import pytest

from shared.sizing_chain import SizingChain, SizingInput


@pytest.fixture
def mt5_input():
    return SizingInput(
        equity=100.0,
        drawdown_pct=0.0,
        is_mt5=True,
        kelly_multiplier=1.0,
        max_position_pct=0.15,
        entry_price=1.0,
        sl_distance=0.01,
    )


def test_mt5_no_budget_ref(mt5_input):
    """MT5 sizing works without leverage budget (backward compat)."""
    result = SizingChain.compute(mt5_input)
    assert result.is_viable
    assert result.skip_reason is None
    assert result.leverage_budget_total == float("inf")


def test_mt5_soft_guard_sufficient_budget():
    lock = threading.Lock()
    ref = [200.0]
    inp = SizingInput(
        equity=100.0,
        drawdown_pct=0.0,
        is_mt5=True,
        kelly_multiplier=1.0,
        max_position_pct=0.15,
        entry_price=1.0,
        sl_distance=0.01,
        leverage_budget_ref=ref,
        leverage_lock=lock,
        leverage_budget_soft=True,
    )
    result = SizingChain.compute(inp)
    assert result.is_viable
    assert ref[0] < 200.0  # budget was decremented


def test_mt5_soft_guard_exhausted_budget():
    lock = threading.Lock()
    ref = [0.0]
    inp = SizingInput(
        equity=100.0,
        drawdown_pct=0.0,
        is_mt5=True,
        kelly_multiplier=1.0,
        max_position_pct=0.15,
        entry_price=1.0,
        sl_distance=0.01,
        leverage_budget_ref=ref,
        leverage_lock=lock,
        leverage_budget_soft=True,
    )
    result = SizingChain.compute(inp)
    assert result.is_viable  # soft guard: still proceeds
    assert result.skip_reason is None
    assert ref[0] == 0.0  # budget unchanged


def test_mt5_hard_guard_exhausted_budget():
    lock = threading.Lock()
    ref = [0.0]
    inp = SizingInput(
        equity=100.0,
        drawdown_pct=0.0,
        is_mt5=True,
        kelly_multiplier=1.0,
        max_position_pct=0.15,
        entry_price=1.0,
        sl_distance=0.01,
        leverage_budget_ref=ref,
        leverage_lock=lock,
        leverage_budget_soft=False,
    )
    result = SizingChain.compute(inp)
    assert not result.is_viable
    assert result.skip_reason == "leverage_exhausted"


def test_paper_budget_still_works():
    lock = threading.Lock()
    ref = [200.0]
    inp = SizingInput(
        equity=100000.0,
        drawdown_pct=0.0,
        is_mt5=False,
        size_scalar=0.15,
        entry_price=100.0,
        sl_distance=2.0,
        leverage_budget_ref=ref,
        leverage_lock=lock,
    )
    result = SizingChain.compute(inp)
    assert result.is_viable
    assert ref[0] < 200.0  # budget decremented


def test_paper_budget_exhausted():
    lock = threading.Lock()
    ref = [0.0]
    inp = SizingInput(
        equity=100000.0,
        drawdown_pct=0.0,
        is_mt5=False,
        size_scalar=0.15,
        entry_price=100.0,
        sl_distance=2.0,
        leverage_budget_ref=ref,
        leverage_lock=lock,
    )
    result = SizingChain.compute(inp)
    assert not result.is_viable
    assert result.skip_reason == "leverage_exhausted"
