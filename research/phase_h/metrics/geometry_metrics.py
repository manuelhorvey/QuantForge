"""Geometry metrics — execution manifold assessment for Phase H.

Extracts:
  - max Sharpe region
  - plateau width (% of grid above 90% max)
  - slope magnitude (stability index)
  - optimal SL/TP cluster shift vs FX baseline
"""

import numpy as np


def compute_geometry_metrics(sweep_summary: dict) -> dict:
    """Compute geometry manifold metrics from an SL/TP sweep summary.

    Args:
        sweep_summary: dict from geometry sweep with best_sharpe, plateau_pct, etc.

    Returns:
        dict with geometry quality metrics
    """
    best = sweep_summary.get('best_sharpe', {})
    return {
        'max_sharpe': sweep_summary.get('max_sharpe', 0.0),
        'best_sl_mult': best.get('sl_mult'),
        'best_tp_mult': best.get('tp_mult'),
        'best_sharpe_value': best.get('sharpe'),
        'best_pf': best.get('pf'),
        'best_n_trades': best.get('n_trades'),
        'plateau_width': sweep_summary.get('plateau_pct', 0.0),
        'n_valid_configs': sweep_summary.get('n_valid_configs', 0),
    }
