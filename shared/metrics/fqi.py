"""Fill Quality Index (FQI).

Measures how faithfully an order was filled relative to ideal execution.
Higher is better — 1.0 = complete fill with zero friction.

FQI = fill_qty_ratio * (1 - 0.50 * gap_fill) * (1 - 0.30 * partial_fill) * max(0, 1 - 0.05 * latency_bars)

All functions are deterministic and stateless — no engine dependency.
"""

from __future__ import annotations

import pandas as pd


def compute_fqi(
    fill_qty_ratio: float,
    gap_fill: bool = False,
    partial_fill: bool = False,
    latency_bars: int = 0,
    gap_penalty: float = 0.50,
    partial_penalty: float = 0.30,
    latency_penalty_per_bar: float = 0.05,
) -> float:
    """Compute Fill Quality Index for a single trade.

    Parameters
    ----------
    fill_qty_ratio : float
        Ratio of filled quantity to requested (0.0 - 1.0).
    gap_fill : bool
        Whether the fill gapped through the limit price.
    partial_fill : bool
        Whether the order was only partially filled.
    latency_bars : int
        Number of bars between signal and fill.
    gap_penalty, partial_penalty : float
        Penalty multipliers for gap and partial fill events.
    latency_penalty_per_bar : float
        Per-bar latency penalty.

    Returns
    -------
    float
        FQI in [0, 1].
    """
    gap_factor = 1.0 - gap_penalty * (1 if gap_fill else 0)
    partial_factor = 1.0 - partial_penalty * (1 if partial_fill else 0)
    latency_factor = max(0.0, 1.0 - latency_penalty_per_bar * latency_bars)

    fqi = fill_qty_ratio * gap_factor * partial_factor * latency_factor
    return round(max(0.0, min(1.0, fqi)), 4)


def compute_fqi_from_df(df: pd.DataFrame, min_trades: int = 3) -> dict[str, float]:
    """Compute average FQI per asset from a DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain columns matching friction domain field names.
    min_trades : int
        Minimum trades required to report FQI for an asset.

    Returns
    -------
    dict[str, float]
        {asset: avg_fqi, ...}
    """
    import pandas as pd

    fill_col = "friction_fill_qty_ratio"
    gap_col = "friction_gap_fill"
    partial_col = "friction_partial_fill"
    latency_col = "friction_latency_bars"

    if fill_col not in df.columns:
        return {}

    results = {}
    asset_col = df.get("asset", pd.Series(index=df.index))
    for asset_name in asset_col.unique():
        grp = df[asset_col == asset_name]
        if len(grp) < min_trades:
            continue

        fqis = []
        for _, row in grp.iterrows():
            fqis.append(
                compute_fqi(
                    fill_qty_ratio=float(row.get(fill_col, 1.0)),
                    gap_fill=bool(row.get(gap_col, False)),
                    partial_fill=bool(row.get(partial_col, False)),
                    latency_bars=int(row.get(latency_col, 0)),
                )
            )
        results[asset_name] = round(float(pd.Series(fqis).mean()), 4)

    return results
