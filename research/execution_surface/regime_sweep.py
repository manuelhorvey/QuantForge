"""Per-Regime Geometry Sweep.

For each asset, finds the optimal (sl_mult, tp_mult) per volatility regime
(low_vol, transition, high_vol) by running a focused 2D grid sweep
on regime-filtered predictions.

Output: data/sandbox/regime_sweep.json
"""

import os, sys, json, logging, argparse
from typing import Optional
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from research.execution_surface.replay_engine import replay, ReplayConfig
from research.execution_surface.monte_carlo import compute_trade_metrics, MIN_TRADES

logger = logging.getLogger("quantforge.execution_surface.regime_sweep")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

SANDBOX_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            'data', 'sandbox')

# Extended grid to test below 0.30 (the grid-edge question)
SL_VALS = np.arange(0.05, 1.05, 0.05)   # 0.05, 0.10, ..., 1.00 (20 values)
TP_VALS = np.arange(1.00, 3.01, 0.25)    # 1.00, 1.25, ..., 3.00 (9 values)
REGIMES = ['low_vol', 'transition', 'high_vol']

ASSETS = ['NZDJPY', 'AUDJPY', 'USDCHF', 'GC', 'EURCAD', 'GBPUSD', 'USDCAD', 'DJI', 'CADJPY', 'EURUSD']


def sweep_regime(predictions: pd.DataFrame, reg: str, spread_bps: float = 0.0) -> list:
    """Sweep (sl, tp) grid for a single regime subset of predictions."""
    sub = predictions[predictions['regime'] == reg].copy()
    if len(sub) < 100:
        logger.warning('  %s: only %d rows, skipping', reg, len(sub))
        return []

    results = []
    total = len(SL_VALS) * len(TP_VALS)
    count = 0

    for sl in SL_VALS:
        for tp in TP_VALS:
            count += 1
            if count % 50 == 0:
                logger.info('    %s: %d/%d', reg, count, total)

            config = ReplayConfig(sl_mult=round(float(sl), 4), tp_mult=round(float(tp), 4), spread_bps=spread_bps)
            trades = replay(sub, config)
            metrics = compute_trade_metrics(trades, round(float(sl), 4), round(float(tp), 4))

            if metrics.get('valid'):
                tp_rate = metrics.get('tp_hit_freq', 0)
                sl_rate = metrics.get('stop_hit_freq', 0)
                metrics['tp_minus_sl'] = round(tp_rate - sl_rate, 4)
                metrics['trade_quality_score'] = round(
                    tp_rate - sl_rate + metrics.get('sharpe', 0) * 0.1, 4
                )
            results.append(metrics)

    return results


def find_best(results: list) -> dict:
    """Find best configs by key metrics."""
    valid = [r for r in results if r.get('valid')]
    if not valid:
        return {}

    def best_by(metric):
        candidates = [r for r in valid if r.get(metric) is not None]
        if not candidates:
            return {}
        best = max(candidates, key=lambda r: r[metric])
        return {
            'sl_mult': best['sl_mult'],
            'tp_mult': best['tp_mult'],
            metric: best[metric],
            'sharpe': best.get('sharpe', 0),
            'tp_rate': best.get('tp_hit_freq', 0),
            'sl_rate': best.get('stop_hit_freq', 0),
            'n_trades': best.get('n_trades', 0),
        }

    return {
        'best_sharpe': best_by('sharpe'),
        'best_tp_minus_sl': best_by('tp_minus_sl'),
        'best_tp_rate': best_by('tp_hit_freq'),
        'lowest_sl': best_by('stop_hit_freq'),
    }


def run(spread_bps: float = 0.0, assets: Optional[list] = None):
    """Run per-regime sweep for all assets."""
    report = {}
    target_assets = assets or ASSETS

    for name in target_assets:
        oos_path = os.path.join(SANDBOX_BASE, name, 'oos_predictions.parquet')
        if not os.path.exists(oos_path):
            logger.warning('%s: no predictions, skipping', name)
            continue

        logger.info('=' * 60)
        logger.info('Sweeping %s (spread=%s bps)...', name, spread_bps)
        logger.info('=' * 60)

        predictions = pd.read_parquet(oos_path)
        asset_result = {'regimes': {}}

        for reg in REGIMES:
            logger.info('  Regime: %s', reg)
            results = sweep_regime(predictions, reg, spread_bps=spread_bps)
            if not results:
                continue
            best = find_best(results)
            asset_result['regimes'][reg] = best

            if best:
                bs = best.get('best_sharpe', {})
                bt = best.get('best_tp_minus_sl', {})
                logger.info('    Best Sharpe:  sl=%.2f tp=%.2f sharpe=%.2f (n=%d)',
                            bs.get('sl_mult', 0), bs.get('tp_mult', 0),
                            bs.get('sharpe', 0), bs.get('n_trades', 0))
                logger.info('    Best TP%%-SL%%: sl=%.2f tp=%.2f tp_minus_sl=%.3f (n=%d)',
                            bt.get('sl_mult', 0), bt.get('tp_mult', 0),
                            bt.get('tp_minus_sl', 0), bt.get('n_trades', 0))

        if asset_result['regimes']:
            report[name] = asset_result

    out_path = os.path.join(SANDBOX_BASE, 'regime_sweep.json')
    with open(out_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    logger.info('Saved regime sweep to %s', out_path)

    print_results(report)
    return report


def print_results(report: dict):
    """Print formatted summary."""
    print('\n' + '=' * 120)
    print('PER-REGIME GEOMETRY SWEEP — BEST SHARPE')
    print('=' * 120)

    for name in sorted(report.keys()):
        print(f'\n{name}:')
        hdr = '  {:>12s} {:>6s} {:>6s} {:>8s} {:>6s} {:>6s} {:>6s} {:>6s}'
        print(hdr.format('Regime', 'SL', 'TP', 'Sharpe', 'TP%', 'SL%', 'TPmSL', 'N'))
        for reg in REGIMES:
            r = report[name]['regimes'].get(reg, {})
            bs = r.get('best_sharpe', {}) or {}
            if not bs:
                continue
            print(hdr.format(
                reg,
                f'{bs.get("sl_mult", 0):.2f}',
                f'{bs.get("tp_mult", 0):.2f}',
                f'{bs.get("sharpe", 0):.2f}',
                f'{bs.get("tp_rate", 0)*100:.0f}%',
                f'{bs.get("sl_rate", 0)*100:.0f}%',
                f'{bs.get("tp_rate", 0)*100 - bs.get("sl_rate", 0)*100:.0f}%',
                str(bs.get('n_trades', 0)),
            ))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Per-regime geometry sweep')
    parser.add_argument('--spread', type=float, default=0.0, help='Spread cost in bps')
    parser.add_argument('--assets', nargs='+', help='Assets to sweep (default: all)')
    args = parser.parse_args()
    run(spread_bps=args.spread, assets=args.assets)
