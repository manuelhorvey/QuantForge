"""Calibrate regime_conviction_flip_gate thresholds from historical flip data.

Pipeline:
  1. Load historical regime probabilities and signal/trade data.
  2. For each flip event (signal direction change):
       a. Record regime_margin = abs(P_trend - P_range) at flip bar.
       b. Compute forward PnL over N bars (median holding period from
          TP / vertical-barrier exits only — flips are excluded to avoid
          circularity).
  3. Bin flips by regime_margin decile; report PF, win rate, avg PnL per decile.
  4. Recommended threshold = lowest decile where PF > 1.0.
"""

import numpy as np
import pandas as pd


def _load_clean_holding_periods(trade_log_path: str) -> float:
    """Median holding period from TP / vertical-barrier exits only."""
    trades = pd.read_parquet(trade_log_path)
    natural = trades[trades["exit_reason"].isin(["take_profit", "vertical_barrier"])]
    if natural.empty:
        return 10
    return int(natural["bars_held"].median())


def _extract_flip_events(
    signals: pd.Series,
    regime_margins: pd.Series,
    regime_labels: pd.Series,
    model_confidences: pd.Series,
    close_prices: pd.Series,
) -> pd.DataFrame:
    """Identify bars where signal direction changed versus prior bar."""
    dir_change = signals.diff().abs() > 0
    flip_idx = dir_change[dir_change].index
    return pd.DataFrame({
        "flip_bar": flip_idx,
        "regime_margin": regime_margins.loc[flip_idx].values,
        "regime_label": regime_labels.loc[flip_idx].values,
        "model_confidence": model_confidences.loc[flip_idx].values,
        "close": close_prices.loc[flip_idx].values,
    })


def _forward_pnl(
    close_prices: pd.Series,
    flip_entry_prices: pd.Series,
    flip_sides: pd.Series,
    horizon: int,
) -> pd.Series:
    """PnL over N bars after a flip entry (positive = profitable)."""
    flip_idx = flip_entry_prices.index
    future = close_prices.shift(-horizon)
    ret = (future.loc[flip_idx] - flip_entry_prices) / flip_entry_prices
    direction = flip_sides.map({"LONG": 1, "SHORT": -1})
    return ret * direction


def calibrate_regime_margin_threshold(
    signals: pd.Series,
    regime_margins: pd.Series,
    regime_labels: pd.Series,
    model_confidences: pd.Series,
    close_prices: pd.Series,
    flip_sides: pd.Series,
    trade_log_path: str | None = None,
    horizon: int | None = None,
) -> dict:
    """Run calibration and return recommended threshold + decile breakdown.

    Args:
        signals: signal direction series (1 = LONG, -1 = SHORT, 0 = FLAT).
        regime_margins: regime_margin = abs(P_trend - P_range) at each bar.
        model_confidences: model confidence (0-100 or 0-1) at each bar.
        close_prices: close price series.
        flip_sides: LONG / SHORT label for the new side after each flip.
        trade_log_path: path to trade log parquet for holding period.
        horizon: forward PnL window (default: from trade log median).

    Returns:
        dict with "deciles" (DataFrame) and "recommended_threshold" (float).
    """
    if horizon is None:
        horizon = _load_clean_holding_periods(trade_log_path or "data/processed/trade_log.parquet")

    flips = _extract_flip_events(signals, regime_margins, regime_labels, model_confidences, close_prices)
    if flips.empty:
        return {"deciles": pd.DataFrame(), "recommended_threshold": 0.35}

    # Report sample composition
    if "regime_label" in flips.columns:
        dist = flips["regime_label"].value_counts(normalize=True)
        print(f"Regime distribution at flip time: {dist.to_dict()}")

    flips["forward_pnl"] = _forward_pnl(close_prices, flips["close"], flip_sides, horizon)

    flips["margin_decile"] = pd.qcut(flips["regime_margin"], 10, labels=False, duplicates="drop")
    decile_stats = (
        flips.groupby("margin_decile")["forward_pnl"]
        .agg(["count", "mean", lambda x: (x > 0).mean()])
        .rename(columns={"mean": "avg_pnl", "<lambda_0>": "win_rate"})
    )
    decile_stats["pf"] = (
        flips.groupby("margin_decile")
        .apply(lambda g: g[g["forward_pnl"] > 0]["forward_pnl"].sum() / max(-g[g["forward_pnl"] < 0]["forward_pnl"].sum(), 1e-9))
    )

    above_one = decile_stats[decile_stats["pf"] > 1.0]
    recommended = above_one.index.min() if not above_one.empty else 0

    margin_bounds = (
        flips.groupby("margin_decile")["regime_margin"]
        .agg(["min", "max"])
    )
    decile_stats = decile_stats.join(margin_bounds)

    return {
        "deciles": decile_stats,
        "recommended_threshold": margin_bounds.loc[recommended, "min"] if isinstance(recommended, (int, np.integer)) and recommended in margin_bounds.index else 0.25,
        "total_flips": len(flips),
        "horizon_bars": horizon,
        "flip_pnl_mean": flips["forward_pnl"].mean(),
        "flip_win_rate": (flips["forward_pnl"] > 0).mean(),
    }


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    print("See run_phase_h.py for integration with the phase H pipeline.")
    print("Usage:")
    print("  from research.phase_h.flip_threshold_calibration import calibrate_regime_margin_threshold")
    print("  result = calibrate_regime_margin_threshold(signals, margins, labels, confs, prices, sides)")
    print("  print(result['recommended_threshold'])")
