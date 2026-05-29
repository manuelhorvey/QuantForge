"""Shadow divergence and counterfactual comparison metrics.

Compares live execution outcomes against shadow (counterfactual) outcomes
from alternative SL/TP configurations.

All functions are deterministic and stateless — no engine dependency.
"""

from __future__ import annotations

from typing import Any


def compute_shadow_divergence(
    shadow_records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute divergence statistics between shadow and live execution.

    Parameters
    ----------
    shadow_records : list[dict]
        List of ShadowTradeRecord dicts with fields:
        exit_reason, live_exit_reason, realized_r, live_realized_r, alt_label.

    Returns
    -------
    dict with divergence rates, R-delta stats, and per-label breakdown.
    """
    import pandas as pd

    if not shadow_records:
        return {
            "n": 0,
            "divergence_rate": 0.0,
            "reason_divergence_rate": 0.0,
            "avg_r_delta": 0.0,
            "r_delta_std": 0.0,
            "by_label": {},
        }

    df = pd.DataFrame(shadow_records)

    n = len(df)
    shadow_r = df.get("realized_r", 0)
    live_r = df.get("live_realized_r", 0)
    r_delta = shadow_r - live_r
    reason_same = df.get("exit_reason", "") == df.get("live_exit_reason", "")

    divergence_rate = float(reason_same.mean())
    overall = {
        "n": n,
        "divergence_rate": round(1.0 - divergence_rate, 4),
        "avg_r_delta": round(float(r_delta.mean()), 4),
        "r_delta_std": round(float(r_delta.std()), 4),
        "shadow_avg_r": round(float(shadow_r.mean()), 4),
        "live_avg_r": round(float(live_r.mean()), 4),
        "shadow_win_rate": round(float((shadow_r > 0).mean()), 4),
        "live_win_rate": round(float((live_r > 0).mean()), 4),
    }

    by_label = {}
    label_col = df.get("alt_label", pd.Series(["default"] * n))
    for label in label_col.unique():
        mask = label_col == label
        grp = df[mask]
        gn = len(grp)
        gr_delta = grp.get("realized_r", 0) - grp.get("live_realized_r", 0)
        gr_same = grp.get("exit_reason", "") == grp.get("live_exit_reason", "")
        gr_divergence = float(gr_same.mean()) if gn > 0 else 0.0
        by_label[label] = {
            "n": gn,
            "divergence_rate": round(1.0 - gr_divergence, 4),
            "avg_r_delta": round(float(gr_delta.mean()), 4),
            "shadow_avg_r": round(float(grp.get("realized_r", 0).mean()), 4),
            "live_avg_r": round(float(grp.get("live_realized_r", 0).mean()), 4),
        }

    return {"overall": overall, "by_label": by_label}


def compute_r_delta_distribution(
    shadow_records: list[dict[str, Any]],
    bins: int = 20,
) -> dict[str, Any]:
    """Compute the distribution of R-multiple differences (shadow - live).

    Parameters
    ----------
    shadow_records : list[dict]
        List of ShadowTradeRecord dicts.
    bins : int
        Number of histogram bins.

    Returns
    -------
    dict with histogram, quartiles, and outlier counts.
    """
    import numpy as np
    import pandas as pd

    if not shadow_records:
        return {"histogram": [], "quartiles": {}, "outliers": {"n_gt_1": 0, "n_lt_minus1": 0}}

    df = pd.DataFrame(shadow_records)
    r_delta = df.get("realized_r", 0) - df.get("live_realized_r", 0)
    r_delta = r_delta.dropna()

    if len(r_delta) == 0:
        return {"histogram": [], "quartiles": {}, "outliers": {"n_gt_1": 0, "n_lt_minus1": 0}}

    hist, edges = np.histogram(r_delta, bins=bins)
    histogram = [
        {"bin_start": round(float(edges[i]), 4), "bin_end": round(float(edges[i + 1]), 4), "count": int(hist[i])}
        for i in range(len(hist))
    ]

    quartiles = {
        "q1": round(float(r_delta.quantile(0.25)), 4),
        "median": round(float(r_delta.median()), 4),
        "q3": round(float(r_delta.quantile(0.75)), 4),
        "min": round(float(r_delta.min()), 4),
        "max": round(float(r_delta.max()), 4),
    }

    outliers = {
        "n_gt_1": int((r_delta > 1.0).sum()),
        "n_lt_minus1": int((r_delta < -1.0).sum()),
    }

    for b in histogram:
        b["count"] = int(b["count"])

    return {"histogram": histogram, "quartiles": quartiles, "outliers": outliers}
