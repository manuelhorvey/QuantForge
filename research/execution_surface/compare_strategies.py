#!/usr/bin/env python3
"""Compare base plateau vs regime-optimized vs meta-model-improved.

Runs all three replay strategies on OOS predictions for each asset
and prints a side-by-side comparison table.

Usage:
    python -m research.execution_surface.compare_strategies
"""

import json
import logging
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from research.execution_surface.regime_geometry import get_plateau_center, to_replay_config
from research.execution_surface.replay_engine import (
    ReplayConfig,
    ReplayRegimeConfig,
    replay,
    replay_meta_geometry,
    replay_regime,
)
from shared.meta_labeling import MetaModel, compute_vol_zscore, encode_regime

logging.basicConfig(level=logging.WARNING, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger('compare')
logger.setLevel(logging.INFO)

SANDBOX_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            'data', 'sandbox')

TARGET_ASSETS = ['NZDJPY', 'AUDJPY', 'USDCHF', 'GC', 'EURCAD', 'GBPUSD', 'USDCAD', 'DJI']


def compute_metrics(trades: pd.DataFrame) -> dict:
    """Compute trade-level metrics."""
    if len(trades) == 0:
        return {'trades': 0, 'sharpe': 0, 'win_rate': 0, 'avg_r': 0, 'med_r': 0,
                'avg_ret': 0, 'total_ret': 0, 'std_ret': 0, 'max_dd': 0}

    returns = trades['return_pct'].values
    r_mult = trades['realized_r'].values if 'realized_r' in trades else returns

    sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(252)) if np.std(returns) > 1e-8 else 0
    win_rate = float(np.mean(returns > 0))
    avg_r = float(np.mean(r_mult))
    med_r = float(np.median(r_mult))
    avg_ret = float(np.mean(returns))
    total_ret = float(np.sum(returns))
    std_ret = float(np.std(returns))

    cum = np.cumsum(returns)
    running_max = np.maximum.accumulate(cum)
    dd = cum - running_max
    max_dd = float(np.min(dd))

    tp_pct = float(np.mean(trades['reason'] == 'tp')) if 'reason' in trades else 0
    sl_pct = float(np.mean(trades['reason'] == 'sl')) if 'reason' in trades else 0
    flip_pct = float(np.mean(trades['reason'] == 'flip')) if 'reason' in trades else 0

    return {
        'trades': len(trades),
        'sharpe': round(sharpe, 4),
        'win_rate': round(win_rate, 4),
        'avg_r': round(avg_r, 4),
        'med_r': round(med_r, 4),
        'avg_ret': round(avg_ret, 6),
        'total_ret': round(total_ret, 4),
        'std_ret': round(std_ret, 6),
        'max_dd': round(max_dd, 6),
        'tp_pct': round(tp_pct, 4),
        'sl_pct': round(sl_pct, 4),
        'flip_pct': round(flip_pct, 4),
    }


def run_base(predictions: pd.DataFrame, sl_mult: float, tp_mult: float) -> pd.DataFrame:
    """Baseline: fixed plateau geometry."""
    cfg = ReplayConfig(sl_mult=sl_mult, tp_mult=tp_mult)
    return replay(predictions, cfg)


def run_regime(predictions: pd.DataFrame, regime_cfg: ReplayRegimeConfig) -> pd.DataFrame:
    """Regime-optimized: per-regime geometry from TUNED_GEOMETRIES."""
    return replay_regime(predictions, regime_cfg)


def run_meta(predictions: pd.DataFrame, regime_cfg: ReplayRegimeConfig) -> tuple:
    """Meta-improved: regime geometry + meta-model per-trade adjustments.

    Returns (trades_df, meta_eval_dict) where meta_eval_dict contains
    holdout AUC, precision, recall, F1, and feature importances.
    """
    eval_results = {'auc': None, 'precision': None, 'recall': None, 'f1': None,
                    'feature_importance': {}, 'test_n': 0, 'skip_rate': 0.0}

    # Pass 1: baseline regime replay to collect training trades
    trades_pass1 = replay_regime(predictions, regime_cfg)
    if len(trades_pass1) < 50:
        logger.info('  only %d pass1 trades, skipping meta', len(trades_pass1))
        return trades_pass1, eval_results

    feature_rows = []
    labels = []
    close_series = predictions['close']
    regime_series = predictions.get('regime', pd.Series(index=predictions.index))
    regime_changed = regime_series != regime_series.shift(1)
    regime_changed.iloc[0] = False

    for idx, (_, tr) in enumerate(trades_pass1.iterrows()):
        ret_pct = float(tr.get('return_pct', 0))
        conf = float(tr.get('conf_at_entry', 50)) / 100.0
        reg = str(tr.get('regime', 'unknown'))
        entry_ts = tr.get('entry_time')
        if entry_ts is not None and entry_ts in predictions.index:
            loc = predictions.index.get_loc(entry_ts)
            close_up_to_entry = close_series.iloc[:loc + 1]
            vz = compute_vol_zscore(close_up_to_entry)
            if loc > 0:
                change_indices = regime_changed.iloc[:loc + 1].values.nonzero()[0]
                days_since = loc - change_indices[-1] if len(change_indices) > 0 else loc
            else:
                days_since = 0
        else:
            vz = 0.0
            days_since = 1
        stability_penalty = max(0.0, 1.0 - days_since / 7.0)
        feature_rows.append({
            'primary_confidence': conf,
            'regime_state_encoded': encode_regime(reg),
            'vol_regime_low': 1.0 if reg == 'low_vol' else 0.0,
            'vol_regime_high': 1.0 if reg == 'high_vol' else 0.0,
            'feature_stability_penalty': stability_penalty,
            'vol_zscore': vz,
            'days_since_regime_change': float(days_since),
        })
        labels.append(1 if ret_pct > 0 else 0)

    if len(feature_rows) < 50:
        logger.info('  only %d feature rows for meta training', len(feature_rows))
        return trades_pass1, eval_results

    X_df = pd.DataFrame(feature_rows)
    y = pd.Series(labels)

    # Time-series holdout: train on first 80%, evaluate on last 20%
    split = int(len(X_df) * 0.8)
    X_train, X_test = X_df.iloc[:split], X_df.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]

    if len(X_test) < 10:
        logger.info('  only %d test samples, using all data for training', len(X_test))
        mm = MetaModel()
        mm.train(X_df, y)
        return replay_meta_geometry(predictions, regime_cfg, mm), eval_results

    # Train meta-model on training split
    mm = MetaModel()
    mm.train(X_train, y_train)

    # Holdout evaluation
    from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score

    X_test_scaled = mm.scaler.transform(X_test[mm.feature_names].values)
    test_probas = mm.model.predict_proba(X_test_scaled)[:, 1]
    test_preds = (test_probas >= 0.5).astype(int)
    eval_results = {
        'auc': round(float(roc_auc_score(y_test, test_probas)), 4),
        'precision': round(float(precision_score(y_test, test_preds, zero_division=0)), 4),
        'recall': round(float(recall_score(y_test, test_preds, zero_division=0)), 4),
        'f1': round(float(f1_score(y_test, test_preds, zero_division=0)), 4),
        'test_n': int(len(X_test)),
        'train_n': int(len(X_train)),
        'skip_rate': 0.0,
    }

    # Feature importance from logistic regression coefficients (abs + scaled)
    coefs = mm.model.coef_[0]
    scaled_imp = {}
    for name, coef in zip(mm.feature_names, coefs):
        scaled_imp[name] = round(abs(coef), 4)
    eval_results['feature_importance'] = dict(sorted(
        scaled_imp.items(), key=lambda x: x[1], reverse=True
    ))

    # Compute skip rate from pass 2 replay
    mm_full = MetaModel()
    mm_full.train(X_df, y)  # re-train on full data for actual pass 2
    trades_meta = replay_meta_geometry(predictions, regime_cfg, mm_full)
    if len(trades_pass1) > 0:
        eval_results['skip_rate'] = round(1.0 - len(trades_meta) / len(trades_pass1), 4)

    return trades_meta, eval_results


def _trades_to_daily(trades: pd.DataFrame, index: pd.DatetimeIndex) -> pd.Series:
    """Convert trade records to daily return series aligned to index."""
    daily = pd.Series(0.0, index=index)
    for _, tr in trades.iterrows():
        exit_ts = tr.get('exit_time')
        if exit_ts is not None and exit_ts in daily.index:
            daily.loc[exit_ts] = float(tr.get('return_pct', 0))
    return daily


def main():
    results = {}
    portfolio_base = {}
    portfolio_regime = {}
    common_index = None

    for name in TARGET_ASSETS:
        oos_path = os.path.join(SANDBOX_BASE, name, 'oos_predictions.parquet')
        if not os.path.exists(oos_path):
            logger.warning('No OOS predictions for %s, skipping', name)
            continue

        logger.info('=' * 70)
        logger.info('Processing %s', name)
        predictions = pd.read_parquet(oos_path)
        logger.info('  %d rows, %.0f-%.0f', len(predictions),
                    predictions.index[0].year, predictions.index[-1].year)

        # Get plateau center for base config
        plateau = get_plateau_center(name)
        if plateau is None:
            logger.warning('  no plateau center for %s, using defaults', name)
            plateau = {'sl_mult': 0.52, 'tp_mult': 1.96}
        base_sl, base_tp = plateau['sl_mult'], plateau['tp_mult']

        # Build regime config from TUNED_GEOMETRIES
        regime_cfg = to_replay_config(name)

        # Run all three strategies
        trades_base = run_base(predictions, base_sl, base_tp)
        trades_regime = run_regime(predictions, regime_cfg)
        trades_meta, meta_eval = run_meta(predictions, regime_cfg)

        portfolio_base[name] = _trades_to_daily(trades_base, predictions.index)
        portfolio_regime[name] = _trades_to_daily(trades_regime, predictions.index)
        if common_index is None:
            common_index = predictions.index

        metrics_base = compute_metrics(trades_base)
        metrics_regime = compute_metrics(trades_regime)
        metrics_meta = compute_metrics(trades_meta)

        results[name] = {
            'base': metrics_base,
            'regime': metrics_regime,
            'meta': metrics_meta,
            'meta_eval': meta_eval,
        }

        # Per-asset summary line
        b_sharpe = metrics_base['sharpe']
        r_sharpe = metrics_regime['sharpe']
        m_sharpe = metrics_meta['sharpe']
        b_trades = metrics_base['trades']
        r_trades = metrics_regime['trades']
        m_trades = metrics_meta['trades']
        b_win = metrics_base['win_rate']
        r_win = metrics_regime['win_rate']
        m_win = metrics_meta['win_rate']
        print(f"\n{name}  (base sl={base_sl:.2f} tp={base_tp:.2f})")
        print(f"  {'':>15} {'Trades':>8} {'Sharpe':>8} {'Win%':>8} {'AvgR':>8} {'TP%':>8} {'SL%':>8}")
        print(f"  {'Base':>15} {b_trades:>8d} {b_sharpe:>8.2f} {b_win:>7.1%} {metrics_base['avg_r']:>8.2f} {metrics_base['tp_pct']:>7.1%} {metrics_base['sl_pct']:>7.1%}")
        print(f"  {'Regime':>15} {r_trades:>8d} {r_sharpe:>8.2f} {r_win:>7.1%} {metrics_regime['avg_r']:>8.2f} {metrics_regime['tp_pct']:>7.1%} {metrics_regime['sl_pct']:>7.1%}")
        print(f"  {'Meta':>15} {m_trades:>8d} {m_sharpe:>8.2f} {m_win:>7.1%} {metrics_meta['avg_r']:>8.2f} {metrics_meta['tp_pct']:>7.1%} {metrics_meta['sl_pct']:>7.1%}")
        if meta_eval.get('auc') is not None:
            print(f"  {'Meta AUC':>15} {meta_eval['auc']:>8.4f}  P={meta_eval['precision']:.2f} R={meta_eval['recall']:.2f} F1={meta_eval['f1']:.2f}  "
                  f"train={meta_eval['train_n']} test={meta_eval['test_n']} skip={meta_eval['skip_rate']:.1%}")
            imp = meta_eval.get('feature_importance', {})
            top = list(imp.items())[:3]
            print(f"  {'Top features':>15} {' | '.join(f'{k}={v:.3f}' for k, v in top)}")

    # Save to JSON
    out_path = os.path.join(SANDBOX_BASE, 'strategy_comparison.json')
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    logger.info('Saved comparison to %s', out_path)

    # Final summary
    print('\n' + '=' * 70)
    print(f'{"STRATEGY COMPARISON SUMMARY":^70}')
    print('=' * 70)
    header = f"{'Asset':>10} {'Base S':>8} {'Reg S':>8} {'Meta S':>8} {'BaseT':>7} {'RegT':>7} {'MetaT':>7} {'B->R':>8} {'R->M':>8} {'B->M':>8}"
    print(header)
    print('-' * len(header))
    for name in TARGET_ASSETS:
        if name not in results:
            continue
        r = results[name]
        b_sharpe = r['base']['sharpe']
        r_sharpe = r['regime']['sharpe']
        m_sharpe = r['meta']['sharpe']
        b_trades = r['base']['trades']
        r_trades = r['regime']['trades']
        m_trades = r['meta']['trades']
        b2r = f"{((r_sharpe - b_sharpe) / abs(b_sharpe) * 100) if b_sharpe != 0 else 0:+.1f}%"
        r2m = f"{((m_sharpe - r_sharpe) / abs(r_sharpe) * 100) if r_sharpe != 0 else 0:+.1f}%"
        b2m = f"{((m_sharpe - b_sharpe) / abs(b_sharpe) * 100) if b_sharpe != 0 else 0:+.1f}%"
        print(f"{name:>10} {b_sharpe:>8.2f} {r_sharpe:>8.2f} {m_sharpe:>8.2f} {b_trades:>7d} {r_trades:>7d} {m_trades:>7d} {b2r:>8} {r2m:>8} {b2m:>8}")

    # Portfolio-level equal-weighted comparison
    if portfolio_base and common_index is not None:
        base_df = pd.DataFrame({n: portfolio_base[n] for n in portfolio_base})
        regime_df = pd.DataFrame({n: portfolio_regime[n] for n in portfolio_regime})
        n_assets = len(portfolio_base)

        port_base = base_df.sum(axis=1) / n_assets
        port_regime = regime_df.sum(axis=1) / n_assets

        def port_metrics(series):
            sr = float(np.mean(series) / np.std(series) * np.sqrt(252)) if np.std(series) > 1e-8 else 0
            ann_ret = float(np.mean(series) * 252)
            ann_vol = float(np.std(series) * np.sqrt(252))
            cum = np.cumsum(series.values)
            dd = cum - np.maximum.accumulate(cum)
            max_dd = float(np.min(dd))
            calmar = float(ann_ret / abs(max_dd)) if max_dd < 0 else 0
            return sr, ann_ret, ann_vol, max_dd, calmar

        b_sr, b_ret, b_vol, b_dd, b_cal = port_metrics(port_base)
        r_sr, r_ret, r_vol, r_dd, r_cal = port_metrics(port_regime)

        print('\n' + '=' * 70)
        print(f'{"PORTFOLIO (EQUAL-WEIGHTED, N=" + str(n_assets) + ")":^70}')
        print('=' * 70)
        print(f"  {'':>15} {'Sharpe':>8} {'Ann.Ret':>8} {'Ann.Vol':>8} {'MaxDD':>8} {'Calmar':>8}")
        print(f"  {'Base':>15} {b_sr:>8.2f} {b_ret:>7.1%} {b_vol:>7.1%} {b_dd:>7.1%} {b_cal:>8.2f}")
        print(f"  {'Regime':>15} {r_sr:>8.2f} {r_ret:>7.1%} {r_vol:>7.1%} {r_dd:>7.1%} {r_cal:>8.2f}")
        b2r_port = ((r_sr - b_sr) / abs(b_sr) * 100) if b_sr != 0 else 0
        print(f"  {'Lift':>15} {b2r_port:>+7.1f}%")

        # Monte Carlo block bootstrap for confidence intervals
        print('\n' + '-' * 70)
        print('BOOTSTRAP CONFIDENCE INTERVALS (1000 paths, block=21d)')
        print('-' * 70)

        def block_bootstrap(series: pd.Series, n_paths: int = 1000,
                            block_len: int = 21, seed: int = 42) -> np.ndarray:
            """Block bootstrap with replacement, preserving time structure."""
            rng = np.random.default_rng(seed)
            vals = series.values
            n = len(vals)
            paths = np.zeros((n_paths, n))

            for p in range(n_paths):
                pos = 0
                while pos < n:
                    start = rng.integers(0, max(1, n - block_len))
                    block = vals[start:start + block_len]
                    end = min(pos + len(block), n)
                    paths[p, pos:end] = block[:end - pos]
                    pos = end
            return paths

        def compute_path_metrics(path: np.ndarray) -> tuple:
            sr = float(np.mean(path) / np.std(path) * np.sqrt(252)) if np.std(path) > 1e-8 else 0
            ann_ret = float(np.mean(path) * 252)
            ann_vol = float(np.std(path) * np.sqrt(252))
            cum = np.cumsum(path)
            dd = cum - np.maximum.accumulate(cum)
            max_dd = float(np.min(dd))
            calmar = float(ann_ret / abs(max_dd)) if max_dd < 0 else 0
            return sr, ann_ret, ann_vol, max_dd, calmar

        paths_base = block_bootstrap(port_base)
        paths_regime = block_bootstrap(port_regime)

        base_metrics = np.array([compute_path_metrics(p) for p in paths_base])
        regime_metrics = np.array([compute_path_metrics(p) for p in paths_regime])

        def ci(arr):
            return (f'{np.percentile(arr, 5):.2f}', f'{np.median(arr):.2f}', f'{np.percentile(arr, 95):.2f}')

        print(f"  {'':>15} {'Sharpe (P5/P50/P95)':>28}")
        print(f"  {'Base':>15}   {ci(base_metrics[:, 0])[0]:>6} / {ci(base_metrics[:, 0])[1]:>6} / {ci(base_metrics[:, 0])[2]:>6}")
        print(f"  {'Regime':>15}   {ci(regime_metrics[:, 0])[0]:>6} / {ci(regime_metrics[:, 0])[1]:>6} / {ci(regime_metrics[:, 0])[2]:>6}")

        lift_p50 = (np.median(regime_metrics[:, 0]) / np.median(base_metrics[:, 0]) - 1) * 100 if np.median(base_metrics[:, 0]) != 0 else 0
        print(f"  {'Lift (median)':>15}   {lift_p50:>+.1f}%")


if __name__ == '__main__':
    main()
