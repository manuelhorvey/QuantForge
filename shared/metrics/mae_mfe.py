"""MAE/MFE normalization and statistics.

MAE (Maximum Adverse Excursion) and MFE (Maximum Favorable Excursion)
measure the worst and best price the trade saw during its lifetime.

Normalization by ATR or entry price enables cross-asset comparison.
Time normalization (per-bar) removes hold-time bias.

All functions are deterministic and stateless — no engine dependency.
"""

from __future__ import annotations

from typing import Any


def normalize_mae_mfe(
    mae: float,
    mfe: float,
    entry_price: float,
    atr_at_entry: float | None = None,
    eps: float = 1e-9,
) -> dict[str, float]:
    """Normalize MAE/MFE by entry price or ATR for cross-asset comparison.

    Parameters
    ----------
    mae : float
        Maximum adverse excursion in price units.
    mfe : float
        Maximum favorable excursion in price units.
    entry_price : float
        Trade entry price.
    atr_at_entry : float | None
        ATR at entry (optional). If provided, normalizes by ATR instead of price.
    eps : float
        Small epsilon to avoid division by zero.

    Returns
    -------
    dict with keys: mae_pct, mfe_pct, mfe_mae_ratio
    """
    if entry_price <= 0:
        return {"mae_pct": 0.0, "mfe_pct": 0.0, "mfe_mae_ratio": 0.0}

    if atr_at_entry is not None and atr_at_entry > 0:
        divisor = atr_at_entry
        label = "atr"
    else:
        divisor = entry_price
        label = "pct"

    mae_norm = abs(mae) / (divisor + eps)
    mfe_norm = abs(mfe) / (divisor + eps)
    ratio = mfe_norm / (mae_norm + eps)

    return {
        f"mae_{label}": round(mae_norm, 6),
        f"mfe_{label}": round(mfe_norm, 6),
        "mfe_mae_ratio": round(ratio, 4),
    }


def compute_mae_mfe_stats(
    records: list[dict[str, Any]],
    atr_col: str | None = None,
) -> dict[str, Any]:
    """Compute aggregate MAE/MFE statistics from a list of attribution record dicts.

    Parameters
    ----------
    records : list[dict]
        List of flattened attribution records (one per trade).
        Expected fields: exit_mae, exit_mfe, entry_price, exit_exit_reason,
        pred_archetype_at_entry, pred_regime_at_entry.
    atr_col : str | None
        Column name for ATR at entry (optional).

    Returns
    -------
    dict with overall stats, by-archetype, and by-regime breakdowns.
    """
    import pandas as pd

    if not records:
        return {
            "overall": {"n": 0, "avg_mae_pct": 0, "avg_mfe_pct": 0, "avg_mfe_mae_ratio": 0},
            "by_archetype": {},
            "by_regime": {},
        }

    df = pd.DataFrame(records)

    mae_col = "exit_mae"
    mfe_col = "exit_mfe"
    price_col = "exec_entry_price" if "exec_entry_price" in df.columns else "entry_price"
    reason_col = "exit_exit_reason"
    arch_col = "pred_archetype_at_entry"
    regime_col = "pred_regime_at_entry"

    def _norm(grp: pd.DataFrame) -> dict:
        mae_vals = grp.get(mae_col, pd.Series([0] * len(grp))).abs()
        mfe_vals = grp.get(mfe_col, pd.Series([0] * len(grp))).abs()
        raw_prices = grp.get(price_col)
        if raw_prices is None:
            raw_prices = pd.Series([1.0] * len(grp))
        prices = raw_prices.replace(0, 1e-9)
        ratios = mfe_vals / (mae_vals + 1e-9)
        raw_reasons = grp.get(reason_col)
        if raw_reasons is None:
            raw_reasons = pd.Series([""] * len(grp))
        tp_mask = raw_reasons == "tp"
        sl_mask = raw_reasons == "sl"
        return {
            "n": len(grp),
            "avg_mae_pct": float((mae_vals / prices).mean()),
            "avg_mfe_pct": float((mfe_vals / prices).mean()),
            "avg_mfe_mae_ratio": float(ratios.mean()),
            "tp_avg_mae_pct": float((mae_vals[tp_mask] / prices[tp_mask]).mean()) if tp_mask.any() else None,
            "sl_avg_mfe_pct": float((mfe_vals[sl_mask] / prices[sl_mask]).mean()) if sl_mask.any() else None,
        }

    result: dict[str, Any] = {"overall": _norm(df), "by_archetype": {}, "by_regime": {}}

    if arch_col in df.columns:
        for arch, grp in df.groupby(arch_col):
            result["by_archetype"][arch] = _norm(grp)

    if regime_col in df.columns:
        for reg, grp in df.groupby(regime_col):
            result["by_regime"][reg] = _norm(grp)

    return result
