"""Attribution waterfall and domain score computation.

Decomposes realized PnL into four causal domains:
  - Prediction: Was the forecast directionally correct?
  - Execution: Did entry timing improve or degrade expectancy?
  - Exit: Did TP geometry preserve convexity?
  - Friction: How much edge died from fills / slippage / delay?

And computes domain scores (0-1) for each trade.

All functions are deterministic and stateless — no engine dependency.
"""

from __future__ import annotations

from typing import Any


def compute_domain_scores(
    record: dict[str, Any],
) -> dict[str, float]:
    """Compute 0-1 domain quality scores for a single attribution record.

    Parameters
    ----------
    record : dict
        Flattened TradeAttributionRecord dict with prefixed fields.

    Returns
    -------
    dict with keys: prediction_score, execution_score, exit_score, friction_score
    """
    # ── Prediction score ────────────────────────────────────────────
    # How confident was the model, and was it directionally correct?
    confidence = record.get("pred_confidence") or 0.0
    forecast_correct = record.get("pred_forecast_direction_correct")
    if forecast_correct is None:
        # Fallback for SQLite schema which might lack this field explicitly
        sig = record.get("side") or record.get("pred_signal")
        exit_px = record.get("exit_price")
        entry_px = record.get("exec_entry_price") or record.get("entry_price")
        if exit_px and entry_px:
            if sig == "long":
                forecast_correct = exit_px > entry_px
            elif sig == "short":
                forecast_correct = exit_px < entry_px

    if forecast_correct is True:
        prediction_score = min(0.5 + confidence * 0.5, 1.0)
    elif forecast_correct is False:
        prediction_score = max(0.0, 1.0 - confidence)
    else:
        prediction_score = 0.5  # neutral / unknown

    # ── Execution score ─────────────────────────────────────────────
    # How efficient was entry timing?
    efficiency = record.get("exec_entry_timing_efficiency")
    if efficiency is None:
        # Fallback for SQLite
        entry_px = record.get("exec_entry_price") or record.get("entry_price")
        mid_px = record.get("exec_mid_price_at_signal")
        if entry_px and mid_px and mid_px > 0:
            efficiency = entry_px / mid_px

    if efficiency is not None and efficiency > 0:
        exec_ratio = min(efficiency, 1.0 / efficiency) if efficiency != 0 else 0
        execution_score = min(exec_ratio, 1.0)
    else:
        execution_score = 0.5

    # Blend in slippage penalty
    entry_slip = abs(record.get("friction_entry_slippage_bps", record.get("exec_entry_slippage_bps", 0)))
    execution_score *= max(0.0, 1.0 - entry_slip / 100.0)

    # ── Exit score ──────────────────────────────────────────────────
    # How well did the exit preserve theoretical R?
    realized_r = record.get("exit_realized_r", record.get("realized_r"))
    theoretical_r = record.get("exit_theoretical_r", record.get("theoretical_r"))
    if theoretical_r is not None and theoretical_r != 0 and realized_r is not None:
        exit_ratio = max(-1.0, min(realized_r / (abs(theoretical_r) + 1e-9), 1.0))
        exit_score = max(0.0, (exit_ratio + 1.0) / 2.0)
    else:
        exit_score = 0.5

    # ── Friction score ──────────────────────────────────────────────
    # How much friction happened at entry and exit?
    exit_slip = abs(record.get("friction_exit_slippage_bps", 0))
    avg_slip = (entry_slip + exit_slip) / 2.0
    friction_base = max(0.0, 1.0 - avg_slip / 75.0)

    gap_fill = record.get("friction_gap_fill", False)
    partial_fill = record.get("friction_partial_fill", False)
    fill_ratio = record.get("friction_fill_qty_ratio", 1.0)
    latency = record.get("friction_latency_bars", 0)

    friction_score = friction_base * fill_ratio
    if gap_fill:
        friction_score *= 0.7
    if partial_fill:
        friction_score *= 0.85
    friction_score *= max(0.0, 1.0 - latency * 0.05)
    friction_score = max(0.0, min(1.0, friction_score))

    return {
        "prediction_score": round(prediction_score, 4),
        "execution_score": round(execution_score, 4),
        "exit_score": round(exit_score, 4),
        "friction_score": round(friction_score, 4),
    }


def compute_waterfall(
    records: list[dict[str, Any]],
) -> dict[str, float]:
    """Decompose aggregate realized PnL into four causal domains.

    Uses Shapley-value-inspired approximation: each domain's contribution
    is estimated from the attribution fields and then scaled to sum to
    the total realized PnL.

    Parameters
    ----------
    records : list[dict]
        List of flattened TradeAttributionRecord dicts.

    Returns
    -------
    dict with keys: prediction_pnl, execution_cost, exit_cost, friction_cost, net_pnl, n
    """
    if not records:
        return {
            "prediction_pnl": 0.0,
            "execution_cost": 0.0,
            "exit_cost": 0.0,
            "friction_cost": 0.0,
            "net_pnl": 0.0,
            "n": 0,
        }

    total_pnl = sum(float(r.get("realized_pnl", r.get("realized_return", 0))) for r in records)
    n = len(records)

    domain_scores = [compute_domain_scores(r) for r in records]
    avg_pred = sum(d["prediction_score"] for d in domain_scores) / n
    avg_exec = sum(d["execution_score"] for d in domain_scores) / n
    avg_exit = sum(d["exit_score"] for d in domain_scores) / n
    avg_friction = sum(d["friction_score"] for d in domain_scores) / n

    total_score = avg_pred + avg_exec + avg_exit + avg_friction
    if total_score == 0:
        return {
            "prediction_pnl": 0.0,
            "execution_cost": 0.0,
            "exit_cost": 0.0,
            "friction_cost": 0.0,
            "net_pnl": total_pnl,
            "n": n,
        }

    # Allocate PnL proportionally to domain scores
    exec_cost = -abs(total_pnl) * (1 - avg_exec) * 0.5  # exec is always a cost
    exit_cost = -abs(total_pnl) * (1 - avg_exit) * 0.3  # exit is mostly a cost
    friction_cost = -abs(total_pnl) * (1 - avg_friction) * 0.5  # friction is a cost

    # Residual: what prediction contributed net of friction
    residual = total_pnl - exec_cost - exit_cost - friction_cost
    prediction_pnl = residual

    return {
        "prediction_pnl": round(prediction_pnl, 4),
        "execution_cost": round(abs(exec_cost), 4),
        "exit_cost": round(abs(exit_cost), 4),
        "friction_cost": round(abs(friction_cost), 4),
        "net_pnl": round(total_pnl, 4),
        "n": n,
    }


def compute_aggregate_domain_scores(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute average domain scores across all records, with breakdowns.

    Parameters
    ----------
    records : list[dict]
        List of flattened TradeAttributionRecord dicts.

    Returns
    -------
    dict with overall, by_archetype, and by_regime breakdowns.
    """
    import pandas as pd

    if not records:
        return {"overall": {}, "by_archetype": {}, "by_regime": {}}

    df = pd.DataFrame(records)
    scores = pd.DataFrame([compute_domain_scores(r) for r in records])

    result: dict[str, Any] = {
        "overall": {col: round(float(scores[col].mean()), 4) for col in scores.columns},
        "by_archetype": {},
        "by_regime": {},
    }

    arch_col = "pred_archetype_at_entry"
    if arch_col in df.columns:
        for arch in df[arch_col].unique():
            mask = df[arch_col].values == arch
            arch_scores = scores[mask]
            result["by_archetype"][arch] = {
                col: round(float(arch_scores[col].mean()), 4) for col in arch_scores.columns
            }

    regime_col = "pred_regime_at_entry"
    if regime_col in df.columns:
        for reg in df[regime_col].unique():
            mask = df[regime_col].values == reg
            reg_scores = scores[mask]
            result["by_regime"][reg] = {col: round(float(reg_scores[col].mean()), 4) for col in reg_scores.columns}

    return result
