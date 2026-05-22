"""Synthetic stress scenario blocks for regime bootstrap hardening.

Extends the empirical CRISIS regime sample (historically ~0.27%) with
parameterized stress blocks calibrated to known historical crisis analogues
but synthesised — not copied — to avoid overfitting to specific episodes.

Injection method:
  Synthetic blocks are pre-pended to each asset's return series before
  regime-classification and bootstrap sampling.  A controlled fraction of
  bootstrap draws land in synthetic CRISIS territory, giving the tail
  distribution plausible density without dominating the empirical signal.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("quantforge.risk.synthetic_stress")


@dataclass(frozen=True)
class StressBlock:
    """A parameterised synthetic stress scenario.

    Each block is a named, auditable stress episode that can be injected
    into the return series before bootstrapping.
    """

    name: str
    source_rationale: str  # e.g. "GFC vol analogue"
    duration_days: int
    daily_return_mean: float  # e.g. -0.0015 (-0.15%/day)
    daily_return_std: float  # daily vol during stress
    vol_multiplier: float  # spread/gap scaling vs normal
    correlation_target: float  # inter-asset corr during the block (0–1)
    liquidity_gap_bps: float  # additional slippage in bps
    weight: float  # sampling weight within CRISIS regime (0–1)


# ── Pre-defined stress block library ───────────────────────────────────
# Each block is named after its *analogue* but parameterised so it is not
# a direct copy of any single historical episode.

STRESS_BLOCK_LIBRARY: list[StressBlock] = [
    StressBlock(
        name="gfc_prolonged",
        source_rationale="GFC 2008 analogue — prolonged vol regime, credit stress, correlated sell-off",
        duration_days=252,
        daily_return_mean=-0.0015,
        daily_return_std=0.025,
        vol_multiplier=2.5,
        correlation_target=0.85,
        liquidity_gap_bps=50.0,
        weight=0.30,
    ),
    StressBlock(
        name="dotcom_prolonged",
        source_rationale="Dot-com 2000-2002 analogue — slow bleed, low correlation, equity-led",
        duration_days=504,
        daily_return_mean=-0.0005,
        daily_return_std=0.018,
        vol_multiplier=1.5,
        correlation_target=0.50,
        liquidity_gap_bps=20.0,
        weight=0.20,
    ),
    StressBlock(
        name="covid_flash",
        source_rationale="COVID-19 March 2020 analogue — sharp crash, rapid recovery, high corr",
        duration_days=20,
        daily_return_mean=-0.015,
        daily_return_std=0.04,
        vol_multiplier=3.0,
        correlation_target=0.90,
        liquidity_gap_bps=80.0,
        weight=0.20,
    ),
    StressBlock(
        name="usd_spike",
        source_rationale="USD liquidity crisis analogue — DXY spike, EM/FX carnage, rates disruption",
        duration_days=63,
        daily_return_mean=-0.0025,
        daily_return_std=0.02,
        vol_multiplier=2.0,
        correlation_target=0.60,
        liquidity_gap_bps=40.0,
        weight=0.15,
    ),
    StressBlock(
        name="flash_crash",
        source_rationale="2010 Flash Crash analogue — single-day tail event with gap risk",
        duration_days=1,
        daily_return_mean=-0.30,
        daily_return_std=0.05,
        vol_multiplier=4.0,
        correlation_target=0.95,
        liquidity_gap_bps=200.0,
        weight=0.10,
    ),
    StressBlock(
        name="carry_collapse",
        source_rationale="2008 FX carry unwind analogue — JPY spike, yield spread compression",
        duration_days=120,
        daily_return_mean=-0.0020,
        daily_return_std=0.022,
        vol_multiplier=2.2,
        correlation_target=0.75,
        liquidity_gap_bps=35.0,
        weight=0.05,
    ),
]


# ══════════════════════════════════════════════════════════════════════
#  I.  Synthetic Block Generation
# ══════════════════════════════════════════════════════════════════════


def generate_stress_returns(
    block: StressBlock,
    n_assets: int,
    seed: int = 42000,
) -> np.ndarray:
    """Generate synthetic daily return array for a single stress block.

    Uses a latent common factor to achieve the target inter-asset
    correlation plus idiosyncratic noise for each pseudo-asset.

    Args:
        block: StressBlock definition
        n_assets: number of assets in the portfolio
        seed: reproducibility seed

    Returns:
        (duration_days, n_assets) array of daily returns
    """
    rng = np.random.default_rng(seed)
    d = block.duration_days
    # Common factor (drives correlation)
    common = rng.normal(0, 1, d)
    # Idiosyncratic noise per asset
    idio = rng.normal(0, 1, (d, n_assets))

    # Mix: common and idiosyncratic, calibrated to correlation_target
    w = math.sqrt(max(0.0, min(1.0, block.correlation_target)))
    returns = np.zeros((d, n_assets))
    for i in range(n_assets):
        mixed = w * common + math.sqrt(1 - w * w) * idio[:, i]
        returns[:, i] = block.daily_return_mean + mixed * block.daily_return_std

    return returns


# ══════════════════════════════════════════════════════════════════════
#  II.  Injection Into Return Series
# ══════════════════════════════════════════════════════════════════════


def inject_synthetic_blocks(
    series_dict: dict[str, np.ndarray],
    blocks: list[StressBlock] | None = None,
    injection_rate: float = 0.25,
    seed: int = 42000,
) -> dict[str, np.ndarray]:
    """Pre-pend synthetic stress blocks to each asset's return series.

    The injection rate controls what fraction of the *total synthetic*
    days are added relative to the original series length.  Each block's
    contribution is proportional to its weight in the library.

    Args:
        series_dict: {name: (n_orig,) daily returns array}
        blocks: stress blocks to inject (default: STRESS_BLOCK_LIBRARY)
        injection_rate: fraction of original length to add as synthetic
        seed: reproducibility

    Returns:
        {name: (n_orig + n_synthetic,) extended return array}
    """
    if blocks is None:
        blocks = STRESS_BLOCK_LIBRARY
    if not blocks:
        return series_dict

    names = list(series_dict.keys())
    n_assets = len(names)
    if n_assets == 0:
        return series_dict

    n_orig = min(len(s) for s in series_dict.values())
    n_synthetic_total = int(n_orig * injection_rate)

    rng = np.random.default_rng(seed)

    # Allocate days to blocks proportionally to weight
    weights = np.array([b.weight for b in blocks])
    weights = weights / weights.sum()
    block_days = np.round(weights * n_synthetic_total).astype(int)
    block_days = np.maximum(block_days, 0)

    # Due to rounding, adjust the last block to match exactly
    diff = n_synthetic_total - block_days.sum()
    if diff != 0 and len(block_days) > 0:
        block_days[-1] = max(0, block_days[-1] + diff)

    # Generate and concatenate synthetic blocks
    synthetic_blocks: list[np.ndarray] = []
    for b, n_days in zip(blocks, block_days):
        if n_days <= 0:
            continue
        block_rng = rng.integers(0, 999999)  # unique seed per block
        # How many repeats of the block do we need?
        n_repeats = max(1, math.ceil(n_days / b.duration_days))
        for rep in range(n_repeats):
            block_rets = generate_stress_returns(b, n_assets, seed=block_rng + rep)
            synthetic_blocks.append(block_rets)

    if not synthetic_blocks:
        return series_dict

    full_synthetic = np.vstack(synthetic_blocks)
    total_synthetic = full_synthetic.shape[0]

    result = {}
    for i, name in enumerate(names):
        syn = full_synthetic[:, i]
        orig = series_dict[name]
        result[name] = np.concatenate([syn, orig])

    n_injected = total_synthetic
    logger.info(
        "Injected %d synthetic stress days (%.1f%% of original %d days) across %d blocks for %d assets",
        n_injected,
        100 * n_injected / max(1, n_orig),
        n_orig,
        len(blocks),
        n_assets,
    )
    return result


def compute_synthetic_fraction(
    series_dict: dict[str, np.ndarray],
    n_synthetic: int,
) -> float:
    """Return the fraction of total series length that is synthetic."""
    n_orig = min(len(s) for s in series_dict.values())
    return n_synthetic / max(1, n_orig + n_synthetic)


# ══════════════════════════════════════════════════════════════════════
#  III.  Bootstrap Validation
# ══════════════════════════════════════════════════════════════════════


@dataclass
class TailValidationResult:
    """Comparison of simulated tail statistics against historical episodes."""

    metric: str
    historical_value: float
    simulated_p50: float
    simulated_p5: float
    simulated_p95: float
    plausible: bool
    note: str = ""


# Known historical crisis statistics for validation.
# These are approximate benchmarks for FX/carry/equity portfolios.
HISTORICAL_CRISIS_BENCHMARKS: dict[str, dict] = {
    "gfc_2008": {
        "max_drawdown_pct": -25.0,
        "recovery_days": 365,
        "sharpe_during": -1.5,
        "annualized_vol_pct": 35.0,
    },
    "covid_2020": {
        "max_drawdown_pct": -15.0,
        "recovery_days": 120,
        "sharpe_during": -2.5,
        "annualized_vol_pct": 45.0,
    },
    "dotcom_2000": {
        "max_drawdown_pct": -20.0,
        "recovery_days": 750,
        "sharpe_during": -0.8,
        "annualized_vol_pct": 25.0,
    },
}


def compute_path_statistics(
    equity: np.ndarray,
    trade_days: int = 252,
) -> dict:
    """Compute summary statistics for a set of equity paths.

    Args:
        equity: (n_paths, n_steps+1) equity curves starting at 1.0
        trade_days: annualisation factor

    Returns:
        dict with 'max_drawdown_pct', 'sharpe', 'annualized_vol_pct'
    """
    n_paths, n_steps = equity.shape
    n_days = n_steps - 1
    years = n_days / trade_days

    # Max drawdown
    running_max = np.maximum.accumulate(equity, axis=1)
    dd = (equity - running_max) / running_max
    max_dd = dd.min(axis=1)

    # Per-path Sharpe and vol
    sharpes = np.zeros(n_paths)
    vols = np.zeros(n_paths)
    for p in range(n_paths):
        daily_r = np.diff(equity[p]) / equity[p, :-1]
        std_r = daily_r.std() if daily_r.std() > 0 else 1e-10
        ann_vol = std_r * math.sqrt(trade_days)
        ann_ret = (equity[p, -1] ** (1.0 / years) - 1.0) if years > 0 else 0.0
        vols[p] = ann_vol
        sharpes[p] = ann_ret / ann_vol

    return {
        "max_drawdown_pct": float(np.median(-max_dd) * 100),
        "sharpe": float(np.median(sharpes)),
        "annualized_vol_pct": float(np.median(vols) * 100),
    }


def validate_tail_statistics(
    equity: np.ndarray,
    trade_days: int = 252,
    benchmarks: dict | None = None,
) -> list[TailValidationResult]:
    """Compare simulated CRISIS-regime tail statistics against historical
    benchmarks and flag implausible values.

    Args:
        equity: (n_paths, n_steps+1) portfolio equity curves
        trade_days: annualisation factor
        benchmarks: dict of crisis name -> benchmark stats
            (default: HISTORICAL_CRISIS_BENCHMARKS)

    Returns:
        list of TailValidationResult
    """
    if benchmarks is None:
        benchmarks = HISTORICAL_CRISIS_BENCHMARKS

    stats = compute_path_statistics(equity, trade_days)

    results = []
    # Compare simulated tail statistics to historical ranges
    all_historical_dds = [b["max_drawdown_pct"] for b in benchmarks.values()]
    all_historical_sharpes = [b["sharpe_during"] for b in benchmarks.values()]
    all_historical_vols = [b["annualized_vol_pct"] for b in benchmarks.values()]

    # Max drawdown plausibility
    sim_dd = stats["max_drawdown_pct"]
    hist_dd_range = (min(all_historical_dds), max(all_historical_dds))
    plausible = hist_dd_range[0] * 1.5 <= -sim_dd <= hist_dd_range[1] * 0.5
    results.append(
        TailValidationResult(
            metric="max_drawdown_pct",
            historical_value=float(np.median(list(b["max_drawdown_pct"] for b in benchmarks.values()))),
            simulated_p50=sim_dd,
            simulated_p5=sim_dd * 0.7,
            simulated_p95=sim_dd * 1.3,
            plausible=plausible,
            note=f"Historical range: {hist_dd_range[0]:.0f}% to {hist_dd_range[1]:.0f}%",
        )
    )

    # Sharpe plausibility
    sim_sharpe = stats["sharpe"]
    hist_sharpe_range = (min(all_historical_sharpes), max(all_historical_sharpes))
    plausible = hist_sharpe_range[0] * 1.5 <= sim_sharpe <= hist_sharpe_range[1] * 0.5
    results.append(
        TailValidationResult(
            metric="sharpe_during_crisis",
            historical_value=float(np.median(list(b["sharpe_during"] for b in benchmarks.values()))),
            simulated_p50=sim_sharpe,
            simulated_p5=sim_sharpe * 0.7,
            simulated_p95=sim_sharpe * 1.3,
            plausible=plausible,
            note=f"Historical range: {hist_sharpe_range[0]:.1f} to {hist_sharpe_range[1]:.1f}",
        )
    )

    # Vol plausibility
    sim_vol = stats["annualized_vol_pct"]
    hist_vol_range = (min(all_historical_vols), max(all_historical_vols))
    plausible = hist_vol_range[0] * 0.5 <= sim_vol <= hist_vol_range[1] * 1.5
    results.append(
        TailValidationResult(
            metric="annualized_vol_pct",
            historical_value=float(np.median(list(b["annualized_vol_pct"] for b in benchmarks.values()))),
            simulated_p50=sim_vol,
            simulated_p5=sim_vol * 0.7,
            simulated_p95=sim_vol * 1.3,
            plausible=plausible and sim_vol > 0,
            note=f"Historical range: {hist_vol_range[0]:.0f}% to {hist_vol_range[1]:.0f}%",
        )
    )

    return results


def print_validation_results(results: list[TailValidationResult]) -> None:
    """Pretty-print tail validation results."""
    print("\n  ── Bootstrap Tail Validation ──")
    header = f"  {'Metric':>28s}  {'Historical':>10s}  {'Sim P50':>9s}  {'Plausible':>10s}"
    print(header)
    print("  " + "- * 60")
    for r in results:
        plausible_str = "YES" if r.plausible else "NO  ← REVIEW"
        print(f"  {r.metric:>28s}  {r.historical_value:>10.1f}  {r.simulated_p50:>9.1f}  {plausible_str:>10s}")
    print()


def regime_fraction_report(
    regimes: np.ndarray,
    n_synthetic: int = 0,
) -> dict[str, float]:
    """Report the fraction of days in each volatility regime.

    Args:
        regimes: (n_days,) array of VolRegime values
        n_synthetic: number of those days that are synthetic stress blocks

    Returns:
        {regime_name: fraction}
    """
    total = len(regimes)
    if total == 0:
        return {}
    from research.risk.execution_physics import VolRegime

    fractions = {}
    for regime in VolRegime:
        frac = float((regimes == regime).mean())
        fractions[regime.name] = round(frac * 100, 2)
    fractions["_n_total"] = total
    fractions["_n_synthetic"] = n_synthetic
    n_crisis = int((regimes == VolRegime.CRISIS).sum())
    fractions["_synthetic_pct_of_crisis"] = round(100 * n_synthetic / max(1, n_crisis), 1)
    return fractions
