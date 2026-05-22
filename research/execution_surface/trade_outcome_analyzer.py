"""Phase H.2 — Trade Outcome Analyzer.

Unified post-trade analytics: TP%/SL%/Time% hit rates, expectancy,
realized R-multiple distribution, regime-stratified breakdowns,
rolling hit rates, holding time profiles, and benchmark comparisons.

Works with both research replay trades and paper trading trade logs.
"""

import os, sys, json, logging
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

logger = logging.getLogger("quantforge.execution_surface.outcome")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

SANDBOX_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            'data', 'sandbox')

# Benchmark thresholds for asymmetric R:R (1:3 to 1:5)
BENCHMARKS = {
    'tp_rate_min': 0.20,
    'tp_rate_max': 0.45,
    'sl_rate_max': 0.60,
    'expectancy_r_min': 0.0,
    'win_rate_min': 0.25,
}


def _normalize_columns(trades: pd.DataFrame) -> pd.DataFrame:
    """Normalize column names from paper trading or research schemas."""
    df = trades.copy()
    rename_map = {
        'entry': 'entry_price',
        'exit': 'exit_price',
        'return': 'return_pct',
        'hold_bars': 'bars',
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})

    required = ['reason', 'return_pct']
    for col in required:
        if col not in df.columns:
            raise ValueError(f"Trade DataFrame missing required column: {col}")

    if 'realized_r' not in df.columns:
        if 'entry_price' in df.columns and 'sl_price' in df.columns:
            risk = (df['entry_price'] - df['sl_price']).abs() / df['entry_price']
            df['realized_r'] = np.where(risk > 0, df['return_pct'] / risk, 0.0)
        else:
            df['realized_r'] = df['return_pct']

    if 'regime' not in df.columns:
        df['regime'] = 'unknown'

    if 'hold_bars' not in df.columns:
        df['hold_bars'] = 0

    return df


def _overall_stats(trades: pd.DataFrame) -> dict:
    """Compute aggregate trade outcome metrics."""
    n = len(trades)
    if n == 0:
        return {}

    total = n
    reasons = trades['reason'].values
    tp_count = int((reasons == 'tp').sum())
    sl_count = int((reasons == 'sl').sum())
    flip_count = int((reasons == 'flip').sum())
    expiry_count = int((reasons == 'expiry').sum())

    returns = trades['return_pct'].values
    gross_win = float(returns[returns > 0].sum()) if len(returns[returns > 0]) > 0 else 0.0
    gross_loss = float(abs(returns[returns < 0].sum())) if len(returns[returns < 0]) > 0 else 0.0

    pf = gross_win / gross_loss if gross_loss > 0 else (float('inf') if gross_win > 0 else 0.0)

    r_values = trades['realized_r'].values
    avg_r = float(np.mean(r_values))
    med_r = float(np.median(r_values))

    tp_sl_total = tp_count + sl_count
    win_rate_tp_sl = tp_count / tp_sl_total if tp_sl_total > 0 else 0.0

    n_winners = int((returns > 0).sum())
    win_rate_pnl = n_winners / n if n > 0 else 0.0

    expectancy_r = 0.0
    if n > 0:
        tp_return = trades[trades['reason'] == 'tp']['realized_r'].mean() if tp_count > 0 else 0.0
        sl_return = trades[trades['reason'] == 'sl']['realized_r'].mean() if sl_count > 0 else 0.0
        flip_return = trades[trades['reason'] == 'flip']['realized_r'].mean() if flip_count > 0 else 0.0
        expiry_return = trades[trades['reason'] == 'expiry']['realized_r'].mean() if expiry_count > 0 else 0.0
        expectancy_r = (
            (tp_count / n) * tp_return +
            (sl_count / n) * sl_return +
            (flip_count / n) * flip_return +
            (expiry_count / n) * expiry_return
        )

    return {
        'n_trades': n,
        'tp_rate': round(tp_count / total, 4),
        'sl_rate': round(sl_count / total, 4),
        'flip_rate': round(flip_count / total, 4),
        'expiry_rate': round(expiry_count / total, 4),
        'win_rate_tp_sl': round(win_rate_tp_sl, 4),
        'win_rate_pnl': round(win_rate_pnl, 4),
        'profit_factor': round(pf, 4),
        'expectancy_return': round(float(np.mean(returns)), 6),
        'expectancy_r': round(expectancy_r, 4),
        'avg_r': round(avg_r, 4),
        'med_r': round(med_r, 4),
        'avg_hold_bars': round(float(trades['hold_bars'].mean()), 2),
        'med_hold_bars': round(float(trades['hold_bars'].median()), 2),
        'avg_return_pct': round(float(np.mean(returns)) * 100, 4),
        'n_winners': n_winners,
        'n_losers': n - n_winners,
    }


def _by_regime(trades: pd.DataFrame) -> dict:
    """Stratify outcome metrics by regime."""
    if 'regime' not in trades.columns:
        return {}
    result = {}
    for regime, group in trades.groupby('regime'):
        if len(group) < 3:
            continue
        stats = _overall_stats(group)
        if stats:
            result[str(regime)] = stats
    return result


def _rolling_hit_rates(trades: pd.DataFrame, window: int = 252) -> dict:
    """Compute rolling window hit rates to detect strategy decay.

    Returns dict with dates, tp_rates, sl_rates, avg_r, flip_rates arrays.
    """
    df = trades.sort_values('exit_time').reset_index(drop=True) if 'exit_time' in trades.columns else trades.reset_index(drop=True)
    if len(df) < window:
        return {'windows': 0, 'dates': [], 'tp_rates': [], 'sl_rates': [], 'avg_r': []}

    dates = []
    tp_rates = []
    sl_rates = []
    avg_r = []
    flip_rates = []

    for i in range(window, len(df) + 1):
        chunk = df.iloc[i - window:i]
        reasons = chunk['reason'].values
        n = len(chunk)
        tp_rates.append(int((reasons == 'tp').sum()) / n)
        sl_rates.append(int((reasons == 'sl').sum()) / n)
        flip_rates.append(int((reasons == 'flip').sum()) / n)
        avg_r.append(float(chunk['realized_r'].mean()))
        if 'exit_time' in chunk.columns:
            dates.append(str(chunk['exit_time'].iloc[-1]))

    return {
        'windows': len(dates),
        'window_size': window,
        'dates': dates,
        'tp_rates': [round(r, 4) for r in tp_rates],
        'sl_rates': [round(r, 4) for r in sl_rates],
        'flip_rates': [round(r, 4) for r in flip_rates],
        'avg_r': [round(r, 4) for r in avg_r],
    }


def _by_exit_type(trades: pd.DataFrame) -> dict:
    """Group metrics by exit reason type."""
    result = {}
    for reason, group in trades.groupby('reason'):
        n = len(group)
        result[str(reason)] = {
            'n_trades': n,
            'avg_r': round(float(group['realized_r'].mean()), 4),
            'med_r': round(float(group['realized_r'].median()), 4),
            'avg_hold_bars': round(float(group['hold_bars'].mean()), 2),
            'avg_return_pct': round(float(group['return_pct'].mean()) * 100, 4),
            'win_rate': round(float((group['return_pct'] > 0).mean()), 4),
        }
    return result


def _holding_time_dist(trades: pd.DataFrame) -> dict:
    """Holding time distribution histogram."""
    hold = trades['hold_bars'].values
    if len(hold) == 0:
        return {}
    bins = [0, 1, 3, 5, 10, 20, 50, 100, 999]
    labels = ['0', '1-2', '3-4', '5-9', '10-19', '20-49', '50-99', '100+']
    counts, _ = np.histogram(hold, bins=bins)
    return {
        'mean': round(float(np.mean(hold)), 2),
        'median': round(float(np.median(hold)), 2),
        'p25': round(float(np.percentile(hold, 25)), 2),
        'p75': round(float(np.percentile(hold, 75)), 2),
        'histogram': {label: int(c) for label, c in zip(labels, counts)},
    }


def _benchmark_check(stats: dict) -> dict:
    """Compare stats against expected benchmarks."""
    checks = {}
    tp_rate = stats.get('tp_rate', 0)
    sl_rate = stats.get('sl_rate', 0)
    expectancy_r = stats.get('expectancy_r', 0)
    win_rate = stats.get('win_rate_tp_sl', stats.get('win_rate_pnl', 0))

    checks['tp_rate_ok'] = BENCHMARKS['tp_rate_min'] <= tp_rate <= BENCHMARKS['tp_rate_max']
    checks['sl_rate_ok'] = sl_rate <= BENCHMARKS['sl_rate_max']
    checks['expectancy_positive'] = expectancy_r > BENCHMARKS['expectancy_r_min']
    checks['win_rate_ok'] = win_rate >= BENCHMARKS['win_rate_min']
    checks['all_ok'] = all(checks.values())

    return checks


def analyze_trade_outcomes(trades: pd.DataFrame, name: str = "",
                           benchmark_config: dict = None) -> dict:
    """Main entry point — compute full outcome analytics.

    Args:
        trades: DataFrame with columns [reason, return_pct, realized_r,
                hold_bars, regime, exit_time, ...]
        name: Asset name for labeling.
        benchmark_config: Optional custom benchmark thresholds.

    Returns:
        dict with overall, by_regime, rolling, by_exit_type,
        holding_time_dist, benchmark_check sections.
    """
    if benchmark_config:
        BENCHMARKS.update(benchmark_config)

    df = _normalize_columns(trades)
    if len(df) < 5:
        return {
            'asset': name,
            'n_trades': len(df),
            'error': f'Insufficient trades ({len(df)} < 5)',
        }

    overall = _overall_stats(df)
    by_regime = _by_regime(df)
    rolling = _rolling_hit_rates(df)
    by_exit = _by_exit_type(df)
    hold_dist = _holding_time_dist(df)
    checks = _benchmark_check(overall)

    return {
        'asset': name,
        'n_trades': overall['n_trades'],
        'overall': overall,
        'by_regime': by_regime,
        'rolling': rolling,
        'by_exit_type': by_exit,
        'holding_time_dist': hold_dist,
        'benchmark_check': checks,
    }


def run_all() -> dict:
    """Run outcome analysis on all Phase C assets at their plateau configs."""
    report = {}

    plateau_path = os.path.join(SANDBOX_BASE, 'sltp_analysis', 'aggregate_report.json')
    if os.path.exists(plateau_path):
        with open(plateau_path) as f:
            aggregate = json.load(f)
    else:
        logger.warning('No aggregate report at %s, using default geometry', plateau_path)
        aggregate = {}

    assets = ['NZDJPY', 'EURAUD', 'USDJPY', 'CADJPY', 'USDCAD', 'AUDJPY',
              'GBPUSD', 'EURCAD', 'CHFJPY', 'GBPJPY', 'USDCHF', 'GC', 'DJI']

    for name in assets:
        oos_path = os.path.join(SANDBOX_BASE, name, 'oos_predictions.parquet')
        if not os.path.exists(oos_path):
            logger.info('%s: no predictions, skipping', name)
            continue

        predictions = pd.read_parquet(oos_path)

        asset_cfg = aggregate.get(name, {})
        if 'error' not in asset_cfg:
            plateau = asset_cfg.get('plateau', {}) or {}
            sl_mult = plateau.get('center_sl_mult', 0.75)
            tp_mult = plateau.get('center_tp_mult', 2.25)
        else:
            sl_mult, tp_mult = 0.75, 2.25

        from research.execution_surface.replay_engine import replay, ReplayConfig
        config = ReplayConfig(sl_mult=sl_mult, tp_mult=tp_mult)
        trades = replay(predictions, config)

        if len(trades) < 5:
            logger.warning('%s: only %d trades, skipping', name, len(trades))
            continue

        result = analyze_trade_outcomes(trades, name=name)
        report[name] = result
        logger.info('%s: TP=%.1f%% SL=%.1f%% Flip=%.1f%% Exp=%.1f%% AvgR=%.2f',
                    name,
                    result['overall']['tp_rate'] * 100,
                    result['overall']['sl_rate'] * 100,
                    result['overall']['flip_rate'] * 100,
                    result['overall']['expiry_rate'] * 100,
                    result['overall']['avg_r'])

    out_path = os.path.join(SANDBOX_BASE, 'trade_outcomes.json')
    with open(out_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    logger.info('Saved trade outcomes to %s', out_path)

    return report


def print_summary(report: dict):
    """Print formatted terminal summary."""
    print('\n' + '=' * 130)
    print('TRADE OUTCOME ANALYSIS')
    print('=' * 130)

    hdr = '  {:>10s} {:>5s} {:>6s} {:>6s} {:>6s} {:>6s} {:>7s} {:>7s} {:>7s} {:>7s} {:>5s}'
    print(hdr.format('Asset', 'N', 'TP%', 'SL%', 'Flip%', 'Exp%',
                     'WR_TP', 'PF', 'AvgR', 'Hold', 'OK?'))
    print('  ' + '-' * 100)

    for name in sorted(report.keys()):
        r = report[name]
        if 'error' in r:
            continue
        o = r['overall']
        ok = r.get('benchmark_check', {}).get('all_ok', False)
        print(hdr.format(
            name,
            o['n_trades'],
            f'{o["tp_rate"]*100:.0f}%',
            f'{o["sl_rate"]*100:.0f}%',
            f'{o["flip_rate"]*100:.0f}%',
            f'{o["expiry_rate"]*100:.0f}%',
            f'{o["win_rate_tp_sl"]*100:.0f}%',
            f'{o["profit_factor"]:.2f}',
            f'{o["avg_r"]:.2f}',
            f'{o["avg_hold_bars"]:.0f}',
            'YES' if ok else 'NO',
        ))

    print('=' * 130)
    print()

    for name in sorted(report.keys()):
        r = report[name]
        if 'error' in r or not r.get('by_regime'):
            continue
        print(f'--- {name} by Regime ---')
        reg_hdr = '  {:>12s} {:>5s} {:>6s} {:>6s} {:>6s} {:>7s} {:>7s}'
        print(reg_hdr.format('Regime', 'N', 'TP%', 'SL%', 'Flip%', 'AvgR', 'Win%'))
        for regime, ro in r['by_regime'].items():
            print(reg_hdr.format(
                regime[:12],
                ro['n_trades'],
                f'{ro["tp_rate"]*100:.0f}%',
                f'{ro["sl_rate"]*100:.0f}%',
                f'{ro["flip_rate"]*100:.0f}%',
                f'{ro["avg_r"]:.2f}',
                f'{ro["win_rate_pnl"]*100:.0f}%',
            ))
        print()


def main():
    report = run_all()
    print_summary(report)


if __name__ == '__main__':
    main()
