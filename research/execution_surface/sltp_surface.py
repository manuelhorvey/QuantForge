"""Phase A.4 — Analyze execution surface: heatmaps, plateau detection, robustness.

For each asset with MC results:
1. Load sltp_surface.parquet
2. Filter to valid configs only
3. Create contour heatmaps (Sharpe, PF)
4. Detect stable plateau regions
5. Compute robustness scores
6. Generate recommendations vs current config
7. Store aggregate report

Output:
- data/sandbox/sltp_analysis/heatmaps/{NAME}_{metric}.png
- data/sandbox/sltp_analysis/aggregate_report.json
"""

import os, sys, json, logging
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from research.execution_surface.monte_carlo import MIN_TRADES

logger = logging.getLogger("quantforge.execution_surface.surface")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

SANDBOX_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            'data', 'sandbox')
ANALYSIS_DIR = os.path.join(SANDBOX_BASE, 'sltp_analysis')
HEATMAP_DIR = os.path.join(ANALYSIS_DIR, 'heatmaps')
PLATEAU_THRESHOLD = 0.90  # >=90% of max Sharpe qualifies as plateau
GRID_RES = 50  # interpolation grid resolution

# Current config values by asset name (from configs/paper_trading.yaml)
CURRENT_CONFIG = {
    'BTC': {'sl': 0.76, 'tp': 3.48},
    'EURGBP': {'sl': 0.52, 'tp': 1.88},
    'GC': {'sl': 0.51, 'tp': 2.94},
    'NZDCHF': {'sl': 0.53, 'tp': 1.80},
    'CHFJPY': {'sl': 0.50, 'tp': 1.70},
    'CADJPY': {'sl': 0.50, 'tp': 1.69},
    'USDCHF': {'sl': 0.52, 'tp': 1.93},
    'EURJPY': {'sl': 0.52, 'tp': 1.65},
    'EURCAD': {'sl': 0.51, 'tp': 1.96},
    'AUDCHF': {'sl': 0.51, 'tp': 1.92},
    'USDJPY': {'sl': 0.51, 'tp': 2.02},
    'USDCAD': {'sl': 0.51, 'tp': 2.03},
    'GBPCHF': {'sl': 0.52, 'tp': 1.65},
    'ES': {'sl': 0.50, 'tp': 4.69},
    'NQ': {'sl': 2.97, 'tp': 4.38},
}


def _load_or_none(path):
    if not os.path.exists(path):
        return None
    return pd.read_parquet(path)


def detect_plateau(surface: pd.DataFrame, metric: str = 'sharpe') -> dict:
    """Detect stable plateau region in the execution surface.

    Uses gridded interpolation to find region where metric >=
    PLATEAU_THRESHOLD * max(metric).

    Returns dict with plateau center, area, gradient, and robustness score.
    """
    valid = surface[surface['valid'] & (surface[metric].notna())].copy()
    if len(valid) < 20:
        return {'error': 'insufficient valid samples'}

    # Create interpolation grid
    sl_grid = np.linspace(valid['sl_mult'].min(), valid['sl_mult'].max(), GRID_RES)
    tp_grid = np.linspace(valid['tp_mult'].min(), valid['tp_mult'].max(), GRID_RES)
    SL_GRID, TP_GRID = np.meshgrid(sl_grid, tp_grid)

    # Simple binning approach: assign each grid point the mean of nearby samples
    metric_grid = np.full_like(SL_GRID, np.nan)
    sl_vals = valid['sl_mult'].values
    tp_vals = valid['tp_mult'].values
    m_vals = valid[metric].values
    sl_step = (sl_grid[1] - sl_grid[0]) / 2
    tp_step = (tp_grid[1] - tp_grid[0]) / 2
    for i in range(GRID_RES):
        for j in range(GRID_RES):
            mask = ((sl_vals >= sl_grid[i] - sl_step) & (sl_vals < sl_grid[i] + sl_step) &
                    (tp_vals >= tp_grid[j] - tp_step) & (tp_vals < tp_grid[j] + tp_step))
            if mask.sum() > 0:
                metric_grid[j, i] = m_vals[mask].mean()

    # Find max and plateau
    valid_mask = ~np.isnan(metric_grid)
    if not valid_mask.any():
        return {'error': 'no valid grid cells'}

    max_val = float(metric_grid[valid_mask].max())
    plateau_mask = metric_grid >= (PLATEAU_THRESHOLD * max_val)

    plateau_area = float(plateau_mask.sum() / valid_mask.sum()) if valid_mask.sum() > 0 else 0.0

    # Plateau center: weighted centroid of plateau region
    if plateau_mask.any():
        plateau_sl = SL_GRID[plateau_mask]
        plateau_tp = TP_GRID[plateau_mask]
        plateau_m = metric_grid[plateau_mask]
        w = plateau_m / plateau_m.sum()
        center_sl = float((plateau_sl * w).sum())
        center_tp = float((plateau_tp * w).sum())
    else:
        center_sl = float(sl_grid[int(valid_mask.mean(axis=0).argmax())])
        center_tp = float(tp_grid[int(valid_mask.mean(axis=1).argmax())])

    # Gradient at center: mean absolute difference to 4 neighbors
    ci = int(np.argmin(np.abs(sl_grid - center_sl)))
    cj = int(np.argmin(np.abs(tp_grid - center_tp)))
    if ci > 0 and ci < GRID_RES - 1 and cj > 0 and cj < GRID_RES - 1:
        neighbors = [metric_grid[cj, ci - 1], metric_grid[cj, ci + 1],
                     metric_grid[cj - 1, ci], metric_grid[cj + 1, ci]]
        neighbors = [n for n in neighbors if not np.isnan(n)]
        gradient = float(np.mean([abs(n - metric_grid[cj, ci]) for n in neighbors])) if neighbors else 0.0
    else:
        gradient = 0.0

    # Trade count at plateau center
    dist = np.sqrt((valid['sl_mult'] - center_sl) ** 2 + (valid['tp_mult'] - center_tp) ** 2)
    closest = valid.loc[dist.idxmin()]
    n_trades_at_center = int(closest['n_trades'])

    # Robustness score: plateau_area * inverse_gradient * trade_count_penalty
    inv_gradient = 1.0 / (1.0 + gradient)
    trade_penalty = min(1.0, n_trades_at_center / 100.0)
    robustness = plateau_area * inv_gradient * trade_penalty

    return {
        'max_value': round(max_val, 4),
        'plateau_threshold': PLATEAU_THRESHOLD,
        'plateau_area': round(plateau_area, 4),
        'center_sl_mult': round(center_sl, 4),
        'center_tp_mult': round(center_tp, 4),
        'gradient_at_center': round(gradient, 6),
        'n_trades_at_center': n_trades_at_center,
        'robustness_score': round(robustness, 4),
    }


def make_heatmap(surface: pd.DataFrame, name: str, metric: str = 'sharpe'):
    """Generate contour heatmap PNG."""
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from matplotlib import cm
    except ImportError:
        logger.warning('matplotlib not available, skipping heatmap for %s', name)
        return

    valid = surface[surface['valid']].copy()
    if len(valid) < 10:
        return

    fig, ax = plt.subplots(figsize=(10, 8))

    # Scatter colored by metric value
    scatter = ax.scatter(
        valid['sl_mult'], valid['tp_mult'],
        c=valid[metric], cmap=cm.viridis,
        s=30, alpha=0.7, edgecolors='none',
    )
    cbar = plt.colorbar(scatter, ax=ax, label=metric.upper())
    cbar.ax.tick_params(labelsize=10)

    ax.set_xlabel('sl_mult', fontsize=12)
    ax.set_ylabel('tp_mult', fontsize=12)
    ax.set_title(f'{name} — Execution Surface ({metric.upper()})', fontsize=14)

    # Mark current config if it exists
    if name in CURRENT_CONFIG:
        cur = CURRENT_CONFIG[name]
        ax.plot(cur['sl'], cur['tp'], 'r*', markersize=18, markeredgecolor='white',
                markeredgewidth=1.0, label='current')
        logger.info('  %s: current config (sl=%.1f, tp=%.1f) marked on heatmap',
                    name, cur['sl'], cur['tp'])

    # Mark plateau center if detectable
    plateau = detect_plateau(surface, metric)
    if 'error' not in plateau and plateau.get('center_sl_mult'):
        ax.plot(plateau['center_sl_mult'], plateau['center_tp_mult'], 'wD',
                markersize=12, markeredgecolor='black', markeredgewidth=1.0,
                label=f'plateau center')
        ax.legend(fontsize=11)

    os.makedirs(HEATMAP_DIR, exist_ok=True)
    out_path = os.path.join(HEATMAP_DIR, f'{name}_{metric}.png')
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    logger.info('  Heatmap saved to %s', out_path)


def analyze_one(name: str, surface: pd.DataFrame) -> dict:
    """Analyze execution surface for one asset."""
    logger.info('=' * 50)
    logger.info('Analyzing %s', name)
    logger.info('=' * 50)

    valid = surface[surface['valid']]
    logger.info('  %d valid configs out of %d total', len(valid), len(surface))

    if len(valid) < MIN_TRADES:
        logger.warning('  %s: insufficient valid configs', name)
        return {'name': name, 'error': 'insufficient valid configs'}

    # Best Sharpe
    best_sharpe = valid.loc[valid['sharpe'].idxmax()]
    logger.info('  Best Sharpe:  %.4f (sl=%.2f, tp=%.2f, trades=%d)',
                best_sharpe['sharpe'], best_sharpe['sl_mult'],
                best_sharpe['tp_mult'], best_sharpe['n_trades'])

    # Best PF
    best_pf = valid.loc[valid['pf'].idxmax()]
    logger.info('  Best PF:      %.2f (sl=%.2f, tp=%.2f, trades=%d)',
                best_pf['pf'], best_pf['sl_mult'],
                best_pf['tp_mult'], best_pf['n_trades'])

    # Plateau detection
    plateau = detect_plateau(surface, 'sharpe')
    if 'error' not in plateau:
        logger.info('  Plateau:  area=%.3f  center(sl=%.2f, tp=%.2f)  gradient=%.6f  robustness=%.4f',
                    plateau['plateau_area'], plateau['center_sl_mult'],
                    plateau['center_tp_mult'], plateau['gradient_at_center'],
                    plateau['robustness_score'])

    # Current config metrics (nearest neighbor)
    current_metrics = None
    if name in CURRENT_CONFIG:
        cur = CURRENT_CONFIG[name]
        dist = np.sqrt((valid['sl_mult'] - cur['sl']) ** 2 + (valid['tp_mult'] - cur['tp']) ** 2)
        closest = valid.loc[dist.idxmin()]
        current_metrics = {
            'sl_mult': cur['sl'],
            'tp_mult': cur['tp'],
            'sharpe': round(float(closest['sharpe']), 4),
            'pf': round(float(closest['pf']), 4),
            'n_trades': int(closest['n_trades']),
            'win_rate': round(float(closest['win_rate']), 4),
            'dist_from_current': round(float(dist.min()), 4),
        }
        logger.info('  Current (sl=%.1f, tp=%.1f):  Sharpe=%.4f  PF=%.2f  trades=%d  (nearest neighbor dist=%.4f)',
                    cur['sl'], cur['tp'],
                    current_metrics['sharpe'], current_metrics['pf'],
                    current_metrics['n_trades'], current_metrics['dist_from_current'])

        # Potential uplift
        plateau_center = plateau.get('center_sl_mult')
        if plateau_center and 'error' not in plateau:
            pdist = np.sqrt((valid['sl_mult'] - plateau['center_sl_mult']) ** 2 +
                            (valid['tp_mult'] - plateau['center_tp_mult']) ** 2)
            pclosest = valid.loc[pdist.idxmin()]
            plateau_sharpe = float(pclosest['sharpe'])
            uplift = round(plateau_sharpe - current_metrics['sharpe'], 4)
            pct = round((plateau_sharpe / current_metrics['sharpe'] - 1) * 100, 1) if current_metrics['sharpe'] != 0 else 0
            current_metrics['plateau_sharpe'] = plateau_sharpe
            current_metrics['uplift'] = uplift
            current_metrics['uplift_pct'] = pct
            logger.info('  Uplift:   plateau=%.4f vs current=%.4f → %+.1f%%',
                        plateau_sharpe, current_metrics['sharpe'], pct)

    return {
        'name': name,
        'best_sharpe': {
            'sl_mult': round(float(best_sharpe['sl_mult']), 4),
            'tp_mult': round(float(best_sharpe['tp_mult']), 4),
            'sharpe': round(float(best_sharpe['sharpe']), 4),
            'pf': round(float(best_sharpe['pf']), 4),
            'n_trades': int(best_sharpe['n_trades']),
        },
        'best_pf': {
            'sl_mult': round(float(best_pf['sl_mult']), 4),
            'tp_mult': round(float(best_pf['tp_mult']), 4),
            'pf': round(float(best_pf['pf']), 4),
            'sharpe': round(float(best_pf['sharpe']), 4),
            'n_trades': int(best_pf['n_trades']),
        },
        'plateau': plateau,
        'current': current_metrics,
        'n_valid_configs': len(valid),
    }


def analyze_all():
    """Analyze all assets with MC results, generate report and heatmaps."""
    os.makedirs(HEATMAP_DIR, exist_ok=True)

    report = {}
    for name in sorted(os.listdir(SANDBOX_BASE)):
        name_path = os.path.join(SANDBOX_BASE, name)
        if not os.path.isdir(name_path) or name in ('evolution', 'historical', 'sltp_analysis'):
            continue
        surface_path = os.path.join(name_path, 'sltp_surface.parquet')
        surface = _load_or_none(surface_path)
        if surface is None:
            continue
        result = analyze_one(name, surface)
        report[name] = result

        # Generate heatmaps
        for metric in ('sharpe', 'pf'):
            try:
                make_heatmap(surface, name, metric)
            except Exception as e:
                logger.warning('%s heatmap failed: %s', metric, e)

    # Save aggregate report
    report_path = os.path.join(ANALYSIS_DIR, 'aggregate_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    logger.info('Aggregate report saved to %s', report_path)

    # Console summary
    print('\n' + '=' * 80)
    print('EXECUTION SURFACE ANALYSIS — SUMMARY')
    print('=' * 80)
    header = f'{"Asset":10s} {"Valid":>6s} {"Best Sharpe":>12s} {"sl":>6s} {"tp":>6s} {"Best PF":>8s} {"Cur Sharpe":>11s} {"Uplift":>8s}'
    print(header)
    print('-' * len(header))
    for name, r in sorted(report.items()):
        if 'error' in r:
            print(f'{name:10s} {"ERROR":>6s}  {r["error"]}')
            continue
        bs = r.get('best_sharpe', {})
        bp = r.get('best_pf', {})
        cur = r.get('current', {})
        plateau = r.get('plateau', {})

        valid = r.get('n_valid_configs', 0)
        best_s = bs.get('sharpe', 0)
        best_sl = bs.get('sl_mult', 0)
        best_tp = bs.get('tp_mult', 0)
        best_pf_val = bp.get('pf', 0)
        cur_sharpe = cur.get('sharpe') if cur else None
        plateau_s = plateau.get('max_value', 0) if 'error' not in plateau else 0
        uplift = f'{((plateau_s / cur_sharpe - 1) * 100):+.1f}%' if (cur_sharpe and cur_sharpe != 0 and plateau_s) else 'N/A'
        cur_str = f'{cur_sharpe:.4f}' if cur_sharpe else 'N/A'
        print(f'{name:10s} {valid:>6d}  {best_s:>8.4f}   {best_sl:>4.2f}  {best_tp:>4.2f}  {best_pf_val:>6.2f}  {cur_str:>11s}  {uplift:>8s}')
    print('=' * 80)
    return report


if __name__ == '__main__':
    analyze_all()
