import numpy as np
import pandas as pd

from research.risk.synthetic_stress import (
    StressBlock,
    STRESS_BLOCK_LIBRARY,
    generate_stress_returns,
    inject_synthetic_blocks,
    compute_path_statistics,
    validate_tail_statistics,
    regime_fraction_report,
    TailValidationResult,
)


def test_library_has_blocks():
    """Library should contain at least 5 pre-defined stress blocks."""
    assert len(STRESS_BLOCK_LIBRARY) >= 5


def test_each_block_has_rationale():
    """Every block must have a non-empty source_rationale."""
    for block in STRESS_BLOCK_LIBRARY:
        assert len(block.source_rationale) > 0


def test_each_block_has_valid_parameters():
    """Basic sanity checks on block parameters."""
    for block in STRESS_BLOCK_LIBRARY:
        assert block.duration_days >= 1
        assert 0.0 <= block.correlation_target <= 1.0
        assert block.weight > 0.0
        assert block.vol_multiplier >= 1.0


def test_generate_stress_returns_shape():
    """Generated returns should have correct shape."""
    block = STRESS_BLOCK_LIBRARY[0]
    returns = generate_stress_returns(block, n_assets=5, seed=42)
    assert returns.shape == (block.duration_days, 5)


def test_generate_stress_returns_mean():
    """Generated returns should approximately match the target mean."""
    block = StressBlock(
        name="test", source_rationale="test",
        duration_days=10000, daily_return_mean=-0.001,
        daily_return_std=0.02, vol_multiplier=2.0,
        correlation_target=0.5, liquidity_gap_bps=50.0, weight=0.5,
    )
    returns = generate_stress_returns(block, n_assets=3, seed=42)
    # With 10000 samples, mean should be within ~3 std errors
    assert abs(returns.mean() - (-0.001)) < 0.003


def test_generate_stress_returns_correlation():
    """Inter-asset correlation should approach the target."""
    block = StressBlock(
        name="test", source_rationale="test",
        duration_days=10000, daily_return_mean=0.0,
        daily_return_std=0.02, vol_multiplier=2.0,
        correlation_target=0.80, liquidity_gap_bps=50.0, weight=0.5,
    )
    returns = generate_stress_returns(block, n_assets=5, seed=42)
    corr = np.corrcoef(returns.T)
    off_diag = corr[np.triu_indices(5, k=1)]
    mean_corr = np.mean(off_diag)
    assert abs(mean_corr - 0.80) < 0.10, f"Mean corr {mean_corr:.3f} != 0.80"


def test_inject_synthetic_blocks_extends_series():
    """Injection should extend each asset's return series."""
    n_orig = 500
    series = {f"asset_{i}": np.random.randn(n_orig) * 0.01
              for i in range(4)}

    extended = inject_synthetic_blocks(series, injection_rate=0.25, seed=42)

    for name in series:
        assert len(extended[name]) > n_orig
        # Original data should be at the end (synthetic prepended)
        np.testing.assert_array_almost_equal(
            extended[name][-n_orig:], series[name])


def test_inject_synthetic_blocks_zero_rate():
    """Zero injection rate should return the original series unchanged."""
    series = {"a": np.random.randn(100)}
    extended = inject_synthetic_blocks(series, injection_rate=0.0, seed=42)
    assert extended["a"] is series["a"]


def test_inject_synthetic_blocks_empty_blocks():
    """Empty block list should return original series."""
    series = {"a": np.random.randn(100)}
    extended = inject_synthetic_blocks(series, blocks=[], injection_rate=0.25)
    assert extended["a"] is series["a"]


def test_compute_path_statistics():
    """Path statistics should return expected keys and plausible values."""
    n_paths, n_steps = 100, 252
    equity = np.ones((n_paths, n_steps))
    # Add some noise
    for p in range(n_paths):
        steps = np.cumprod(1.0 + np.random.randn(n_steps - 1) * 0.01)
        equity[p, 1:] = steps

    stats = compute_path_statistics(equity, trade_days=252)
    assert "max_drawdown_pct" in stats
    assert "sharpe" in stats
    assert "annualized_vol_pct" in stats
    assert stats["annualized_vol_pct"] > 0


def test_validate_tail_statistics_returns_list():
    """Tail validation should return a list of TailValidationResult."""
    n_paths, n_steps = 100, 252
    equity = np.ones((n_paths, n_steps))
    for p in range(n_paths):
        steps = np.cumprod(1.0 + np.random.randn(n_steps - 1) * 0.02)
        equity[p, 1:] = steps

    results = validate_tail_statistics(equity)
    assert len(results) >= 3
    for r in results:
        assert isinstance(r, TailValidationResult)
        assert isinstance(r.plausible, bool)


def test_regime_fraction_report():
    """Regime fraction report should return valid percentages."""
    from research.risk.execution_physics import VolRegime

    regimes = np.array([VolRegime.CALM] * 700 + [VolRegime.ELEVATED] * 200 +
                        [VolRegime.CRISIS] * 100)
    fracs = regime_fraction_report(regimes, n_synthetic=50)
    assert fracs["CALM"] == 70.0
    assert fracs["ELEVATED"] == 20.0
    assert fracs["CRISIS"] == 10.0
    assert "_n_synthetic" in fracs
    assert "_synthetic_pct_of_crisis" in fracs


def test_generate_stress_returns_deterministic():
    """Same seed should produce identical returns."""
    block = STRESS_BLOCK_LIBRARY[0]
    a = generate_stress_returns(block, n_assets=3, seed=12345)
    b = generate_stress_returns(block, n_assets=3, seed=12345)
    np.testing.assert_array_equal(a, b)


def test_inject_synthetic_blocks_preserves_dtype():
    """Injected series should have the same dtype as original."""
    series = {"a": np.random.randn(500).astype(np.float64)}
    extended = inject_synthetic_blocks(series, injection_rate=0.25, seed=42)
    assert extended["a"].dtype == np.float64
