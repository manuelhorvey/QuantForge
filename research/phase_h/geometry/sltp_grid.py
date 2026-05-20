"""Geometry sweep — executes SL/TP grid for an asset's prediction set.

MODE C: isolates execution manifold validity by sweeping SL/TP
multipliers while holding the model fixed.

This is the Phase H equivalent of the Phase A MC sweep, but with
a coarser grid and restricted scope (no retraining, no persistence).
"""

import os, json, logging
import pandas as pd
import numpy as np

logger = logging.getLogger("quantforge.phase_h.geometry_sweep")


SL_MULT_GRID = [0.3, 0.5, 0.75, 1.0, 1.5, 2.5]
TP_MULT_GRID = [0.8, 1.5, 2.25, 3.0, 4.0, 5.0]


def compute_trade_metrics_simple(trades: pd.DataFrame) -> dict:
    """Compute basic trade metrics from a trade DataFrame."""
    if trades.empty or 'return_pct' not in trades.columns:
        return {'valid': False, 'n_trades': 0}

    returns = trades['return_pct'].values
    n = len(returns)

    if n < 10:
        return {'valid': False, 'n_trades': n}

    sharpe = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0.0
    positive = returns[returns > 0]
    negative = returns[returns < 0]
    pf = positive.sum() / abs(negative.sum()) if len(negative) > 0 else float('inf')
    win_rate = (returns > 0).mean()
    expectancy = returns.mean()
    max_dd = 0.0
    cum = np.cumprod(1 + returns)
    running_max = np.maximum.accumulate(cum)
    drawdown = (cum - running_max) / running_max
    max_dd = float(drawdown.min()) if len(drawdown) > 0 else 0.0
    payoff_asym = returns[returns > 0].mean() / abs(returns[returns < 0].mean()) if len(negative) > 0 else float('inf')

    return {
        'valid': True,
        'n_trades': n,
        'sharpe': round(float(sharpe), 4),
        'pf': round(float(pf), 4),
        'win_rate': round(float(win_rate), 4),
        'expectancy': round(float(expectancy), 6),
        'max_dd': round(float(max_dd), 4),
        'payoff_asym': round(float(payoff_asym), 4),
    }


def run_geometry_sweep(
    predictions: pd.DataFrame,
    output_dir: str,
    label: str = 'domain_model',
) -> dict:
    """Run an SL/TP grid sweep over prediction signals.

    Args:
        predictions: DataFrame with [open, high, low, close, signal, ...]
        output_dir: directory to save sweep results
        label: label for this sweep (e.g. 'fx_transfer', 'domain_model')

    Returns:
        dict with sweep summary
    """
    from research.execution_surface.replay_engine import replay, ReplayConfig

    os.makedirs(output_dir, exist_ok=True)
    sweep_results = []

    for sl_mult in SL_MULT_GRID:
        for tp_mult in TP_MULT_GRID:
            config = ReplayConfig(sl_mult=sl_mult, tp_mult=tp_mult)
            trades = replay(predictions, config)
            metrics = compute_trade_metrics_simple(trades)

            entry = {
                'sl_mult': sl_mult,
                'tp_mult': tp_mult,
                **metrics,
            }
            sweep_results.append(entry)

    # Find best Sharpe config
    valid = [r for r in sweep_results if r.get('valid')]
    best_sharpe = max(valid, key=lambda r: r['sharpe']) if valid else {}

    # Plateau detection: % of grid above 90% of max Sharpe
    if best_sharpe and best_sharpe['sharpe'] > 0:
        max_sr = best_sharpe['sharpe']
        threshold_sr = max_sr * 0.9
        plateau_count = sum(1 for r in valid if r['sharpe'] >= threshold_sr)
        n_total = len(SL_MULT_GRID) * len(TP_MULT_GRID)
        plateau_pct = plateau_count / n_total if n_total > 0 else 0
    else:
        max_sr = 0
        plateau_pct = 0

    summary = {
        'label': label,
        'n_sweep_points': len(sweep_results),
        'best_sharpe': {
            'sl_mult': best_sharpe.get('sl_mult'),
            'tp_mult': best_sharpe.get('tp_mult'),
            'sharpe': best_sharpe.get('sharpe'),
            'pf': best_sharpe.get('pf'),
            'n_trades': best_sharpe.get('n_trades'),
        } if best_sharpe else None,
        'plateau_pct': round(float(plateau_pct), 4),
        'max_sharpe': round(float(max_sr), 4),
        'n_valid_configs': len(valid),
    }

    # Save full grid
    grid_path = os.path.join(output_dir, f'grid_{label}.json')
    with open(grid_path, 'w') as f:
        json.dump(sweep_results, f, indent=2, default=str)

    # Save summary
    summary_path = os.path.join(output_dir, f'summary_{label}.json')
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2)

    logger.info('  %s: best SR=%.4f at sl=%.2f tp=%.2f (n=%d) plateau=%.1f%%',
                label, summary['best_sharpe']['sharpe'] if best_sharpe else 0,
                best_sharpe.get('sl_mult', 0), best_sharpe.get('tp_mult', 0),
                best_sharpe.get('n_trades', 0), plateau_pct * 100)

    return summary
