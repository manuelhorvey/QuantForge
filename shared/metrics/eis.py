"""Execution Impact Score (EIS).

Measures how much execution friction degrades raw edge.
Higher is better — 1.0 = perfect frictionless fill, 0.0 = complete execution failure.

EIS = w_s * (1 - slippage_penalty) + w_f * fqi + w_l * (1 - latency_penalty)
  where:
    slippage_penalty = min(entry_slippage_bps / 50, 1.0)
    fqi             = fill quality index (from fqi module)
    latency_penalty = min(latency_bars / 10, 1.0)
    w_s = 0.40, w_f = 0.35, w_l = 0.25

All functions are deterministic and stateless — no engine dependency.
"""

from __future__ import annotations


def compute_eis(
    entry_slippage_bps: float,
    exit_slippage_bps: float,
    fill_qty_ratio: float,
    gap_fill: bool,
    partial_fill: bool,
    latency_bars: int,
    max_slippage_bps: float = 50.0,
    max_latency_bars: int = 10,
    w_slippage: float = 0.40,
    w_fill: float = 0.35,
    w_latency: float = 0.25,
) -> float:
    """Compute Execution Impact Score for a single trade.

    Parameters
    ----------
    entry_slippage_bps : float
        Slippage at entry in basis points.
    exit_slippage_bps : float
        Slippage at exit in basis points (used for FQI weighting).
    fill_qty_ratio : float
        Ratio of filled quantity to requested (0.0 - 1.0).
    gap_fill : bool
        Whether the fill gapped through the limit price.
    partial_fill : bool
        Whether the order was only partially filled.
    latency_bars : int
        Number of bars between signal and fill.
    max_slippage_bps, max_latency_bars : float, int
        Normalization ceilings.
    w_slippage, w_fill, w_latency : float
        Component weights (must sum to 1.0).

    Returns
    -------
    float
        EIS in [0, 1].
    """
    from shared.metrics.fqi import compute_fqi

    slippage_penalty = min(abs(entry_slippage_bps) / max_slippage_bps, 1.0)
    latency_penalty = min(latency_bars / max_latency_bars, 1.0)

    fqi = compute_fqi(fill_qty_ratio, gap_fill, partial_fill, latency_bars)

    eis = w_slippage * (1 - slippage_penalty) + w_fill * fqi + w_latency * (1 - latency_penalty)
    return round(eis, 4)


def compute_eis_from_df(df: pd.DataFrame, min_trades: int = 3) -> dict[str, float]:
    """Compute aggregate EIS per asset from a DataFrame of attribution records.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns matching friction domain field names.
    min_trades : int
        Minimum trades required to report EIS for an asset.

    Returns
    -------
    dict[str, float]
        {asset: eis, ...}
    """
    import pandas as pd

    slippage_col = "friction_entry_slippage_bps"
    fill_col = "friction_fill_qty_ratio"
    gap_col = "friction_gap_fill"
    partial_col = "friction_partial_fill"
    latency_col = "friction_latency_bars"

    required = {slippage_col, fill_col, gap_col, partial_col, latency_col}
    missing = required - set(df.columns)
    if missing:
        return {}

    results = {}
    asset_col = df.get("asset", pd.Series(index=df.index))
    for asset_name in asset_col.unique():
        grp = df[asset_col == asset_name]
        if len(grp) < min_trades:
            continue

        avg_slippage = float(grp.get(slippage_col, 0).mean())
        avg_fill = float(grp.get(fill_col, 1.0).mean())
        avg_gap = grp.get(gap_col, False).mean()
        avg_partial = grp.get(partial_col, False).mean()
        avg_latency = float(grp.get(latency_col, 0).mean())

        # FQI from aggregate values
        from shared.metrics.fqi import compute_fqi

        avg_fqi = compute_fqi(avg_fill, bool(avg_gap > 0.5), bool(avg_partial > 0.5), int(avg_latency))

        slippage_penalty = min(abs(avg_slippage) / 50.0, 1.0)
        latency_penalty = min(avg_latency / 10.0, 1.0)

        eis = 0.40 * (1 - slippage_penalty) + 0.35 * avg_fqi + 0.25 * (1 - latency_penalty)
        results[asset_name] = round(eis, 4)

    return results
