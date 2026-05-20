"""Phase G+ — Persistence-Conditioned Execution Controller.

The key finding from Phase G: persistence IS recoverable from features for
some assets (GBPUSD r=0.51 at k=15), but magnitude is not (Phase E r≈0).

This means: the model knows *when it is right* (transition will persist),
but fixed geometry misprices assets with heterogeneous duration distributions.

The fix: condition SL/TP on predicted persistence at entry time.

Architecture:
  For each bar with a directional signal:
    1. Compute persistence score (P(survive k=7 bars | features))
    2. Bucket into low/mid/high persistence
    3. Map to dynamic (sl_mult, tp_mult)
    4. Open position with dynamic geometry

This converts GBPUSD from a fragile asset into an adaptive one.
"""

import os, sys, json, logging, pickle
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from features.registry import FEATURE_REGISTRY
from research.execution_surface.replay_engine import check_barrier_hit, compute_trade_return, PositionState
from research.execution_surface.monte_carlo import compute_trade_metrics, MIN_TRADES

logger = logging.getLogger("quantforge.execution_surface.persistence_execution")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

SANDBOX_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            'data', 'sandbox')
PERSISTENCE_DIR = os.path.join(SANDBOX_BASE, 'persistence')
EXECUTION_DIR = os.path.join(SANDBOX_BASE, 'persistence_execution')
os.makedirs(EXECUTION_DIR, exist_ok=True)

PERSISTENCE_HORIZON = 7  # strongest medium-term signal

# Dynamic geometry mapping: persistence quantile → (sl_mult, tp_mult)
# Low persistence → tight exit (cut losses fast)
# High persistence → let it run
DYNAMIC_GEOMETRY = {
    'low':  {'sl_mult': 0.5, 'tp_mult': 1.5},   # tight: get out fast
    'mid':  {'sl_mult': 0.75, 'tp_mult': 2.25},  # medium: standard
    'high': {'sl_mult': 1.0, 'tp_mult': 3.0},    # loose: let it breathe
}

FIXED_MEDIUM = {'sl_mult': 0.75, 'tp_mult': 2.25}
FIXED_LOOSE = {'sl_mult': 1.0, 'tp_mult': 3.0}


def load_persistence_model(name: str):
    """Load trained persistence model for an asset at the target horizon."""
    model_dir = os.path.join(PERSISTENCE_DIR, name, 'models')
    model_path = os.path.join(model_dir, f'model_k{PERSISTENCE_HORIZON:02d}.pkl')
    if not os.path.exists(model_path):
        logger.warning('  %s: no persistence model at %s', name, model_path)
        return None
    with open(model_path, 'rb') as f:
        return pickle.load(f)


def compute_persistence_scores(name: str, predictions: pd.DataFrame) -> pd.Series:
    """Compute persistence score (P(survive k bars)) for each bar.

    Rebuilds features and runs the persistence model.
    Returns Series of survival probabilities indexed by prediction timestamps.
    """
    model = load_persistence_model(name)
    if model is None:
        return None

    ticker_map = {c.name: t for t, c in FEATURE_REGISTRY.items()}
    ticker = ticker_map.get(name)
    if ticker is None:
        return None
    contract = FEATURE_REGISTRY[ticker]

    from features.builder import compute_macro_derived, build_features
    import yfinance as yf

    def _normalize(df):
        df = df.copy()
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        if df.index.tz is None:
            df.index = df.index.tz_localize('US/Eastern')
        else:
            df.index = df.index.tz_convert('US/Eastern')
        return df

    def _fetch(t, years=15):
        end = pd.Timestamp.now()
        start = f'{end.year - years}-01-01'
        d = yf.download(t, start=start, end=end.strftime('%Y-%m-%d'), auto_adjust=True, progress=False)
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = [c[0] for c in d.columns]
        d = d.rename(columns={'Close': 'close', 'High': 'high', 'Low': 'low', 'Open': 'open', 'Volume': 'volume'})
        return _normalize(d)

    logger.info('  Rebuilding features for persistence scores...')
    df = _fetch(ticker, years=15)
    macro_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                              'data', 'processed', 'macro_factors.parquet')
    macro = compute_macro_derived(pd.read_parquet(macro_path))
    ref = _fetch('SPY', years=15) if contract.requires_ref else None
    features_df = build_features(df, macro, ref, contract)

    common_idx = predictions.index.intersection(features_df.index)
    if len(common_idx) < 10:
        logger.warning('  %s: insufficient overlap (%d)', name, len(common_idx))
        return None

    features_aligned = features_df.loc[common_idx]
    feature_names = list(contract.features)
    available = [f for f in feature_names if f in features_aligned.columns]
    if not available:
        return None

    X = features_aligned[available].values
    scores = model.predict_proba(X)[:, 1]
    return pd.Series(scores, index=common_idx)


def map_persistence_to_geometry(persistence_score: float,
                                thresholds: tuple = None) -> dict:
    """Map a persistence score to dynamic SL/TP geometry via quantile bucketing.

    Args:
        persistence_score: P(survive k bars | features) ∈ [0, 1]
        thresholds: (low_thresh, mid_thresh) — empirical quantiles of score distribution.
                    If None, uses fixed 0.33/0.67.
    """
    if thresholds is not None:
        low_th, mid_th = thresholds
    else:
        low_th, mid_th = 0.33, 0.67

    if persistence_score < low_th:
        return DYNAMIC_GEOMETRY['low']
    elif persistence_score < mid_th:
        return DYNAMIC_GEOMETRY['mid']
    else:
        return DYNAMIC_GEOMETRY['high']


def replay_dynamic(predictions: pd.DataFrame, persistence_scores: pd.Series,
                   thresholds: tuple = None) -> pd.DataFrame:
    """Replay with persistence-conditioned dynamic SL/TP.

    Uses the same OHC lifecycle simulation as replay_engine.py but
    determines sl_mult/tp_mult per-bar based on persistence score at entry.
    """
    trades = []
    pos = None

    for idx, (timestamp, row) in enumerate(predictions.iterrows()):
        signal = int(row['signal'])
        close = float(row['close'])

        # 1. Check existing position for SL/TP hit
        if pos is not None:
            hit = check_barrier_hit(row, pos)
            if hit is not None:
                reason, exit_price = hit
                ret = compute_trade_return(pos.side, pos.entry_price, exit_price)
                trades.append({
                    'entry_time': pos.entry_time,
                    'exit_time': timestamp,
                    'side': pos.side,
                    'entry_price': pos.entry_price,
                    'exit_price': exit_price,
                    'sl_price': pos.sl_price,
                    'tp_price': pos.tp_price,
                    'reason': reason,
                    'hold_bars': idx - pos.entry_idx,
                    'return_pct': ret,
                    'vol_at_entry': pos.vol_at_entry,
                    'conf_at_entry': pos.conf_at_entry,
                    'persistence_at_entry': pos.__dict__.get('persistence_at_entry', None),
                    'year': int(row['year']),
                    'regime': str(row['regime']),
                    'sl_mult_used': pos.__dict__.get('sl_mult_used', None),
                    'tp_mult_used': pos.__dict__.get('tp_mult_used', None),
                })
                pos = None

        # 2. Determine desired side
        if signal == 2:
            desired = 'long'
        elif signal == 0:
            desired = 'short'
        else:
            continue

        # 3. Get persistence score at this bar (if available)
        persist = persistence_scores.get(timestamp, None) if persistence_scores is not None else None
        if persist is not None and not np.isnan(persist):
            geo = map_persistence_to_geometry(persist, thresholds)
            sl_mult = geo['sl_mult']
            tp_mult = geo['tp_mult']
        else:
            sl_mult = FIXED_MEDIUM['sl_mult']
            tp_mult = FIXED_MEDIUM['tp_mult']

        # 4. Position management
        if pos is None:
            vol = float(row.get('volatility', 0.01))
            if pd.isna(vol) or vol <= 0:
                vol = 0.01
            sl = close * (1 - vol * sl_mult) if desired == 'long' else close * (1 + vol * sl_mult)
            tp = close * (1 + vol * tp_mult) if desired == 'long' else close * (1 - vol * tp_mult)
            pos = PositionState(
                side=desired, entry_price=close, entry_time=timestamp,
                sl_price=sl, tp_price=tp,
                vol_at_entry=vol, conf_at_entry=float(row['confidence']),
                entry_idx=idx,
            )
            pos.sl_mult_used = sl_mult
            pos.tp_mult_used = tp_mult
            pos.persistence_at_entry = persist
        elif pos.side != desired:
            # Hard close before reversal
            ret = compute_trade_return(pos.side, pos.entry_price, close)
            trades.append({
                'entry_time': pos.entry_time,
                'exit_time': timestamp,
                'side': pos.side,
                'entry_price': pos.entry_price,
                'exit_price': close,
                'sl_price': pos.sl_price,
                'tp_price': pos.tp_price,
                'reason': 'flip',
                'hold_bars': idx - pos.entry_idx,
                'return_pct': ret,
                'vol_at_entry': pos.vol_at_entry,
                'conf_at_entry': pos.conf_at_entry,
                'persistence_at_entry': pos.__dict__.get('persistence_at_entry', None),
                'year': int(row['year']),
                'regime': str(row['regime']),
                'sl_mult_used': pos.__dict__.get('sl_mult_used', None),
                'tp_mult_used': pos.__dict__.get('tp_mult_used', None),
            })
            vol = float(row.get('volatility', 0.01))
            if pd.isna(vol) or vol <= 0:
                vol = 0.01
            sl = close * (1 - vol * sl_mult) if desired == 'long' else close * (1 + vol * sl_mult)
            tp = close * (1 + vol * tp_mult) if desired == 'long' else close * (1 - vol * tp_mult)
            pos = PositionState(
                side=desired, entry_price=close, entry_time=timestamp,
                sl_price=sl, tp_price=tp,
                vol_at_entry=vol, conf_at_entry=float(row['confidence']),
                entry_idx=idx,
            )
            pos.sl_mult_used = sl_mult
            pos.tp_mult_used = tp_mult
            pos.persistence_at_entry = persist

    # Close open position
    if pos is not None:
        last_row = predictions.iloc[-1]
        ret = compute_trade_return(pos.side, pos.entry_price, float(last_row['close']))
        trades.append({
            'entry_time': pos.entry_time,
            'exit_time': predictions.index[-1],
            'side': pos.side,
            'entry_price': pos.entry_price,
            'exit_price': float(last_row['close']),
            'sl_price': pos.sl_price,
            'tp_price': pos.tp_price,
            'reason': 'expiry',
            'hold_bars': len(predictions) - 1 - pos.entry_idx,
            'return_pct': ret,
            'vol_at_entry': pos.vol_at_entry,
            'conf_at_entry': pos.conf_at_entry,
            'persistence_at_entry': pos.__dict__.get('persistence_at_entry', None),
            'year': int(last_row['year']),
            'regime': str(last_row['regime']),
            'sl_mult_used': pos.__dict__.get('sl_mult_used', None),
            'tp_mult_used': pos.__dict__.get('tp_mult_used', None),
        })

    if not trades:
        return pd.DataFrame(columns=[
            'entry_time', 'exit_time', 'side', 'entry_price', 'exit_price',
            'sl_price', 'tp_price', 'reason', 'hold_bars', 'return_pct',
            'vol_at_entry', 'conf_at_entry', 'persistence_at_entry',
            'year', 'regime', 'sl_mult_used', 'tp_mult_used',
        ])
    return pd.DataFrame(trades)


def replay_filtered(predictions: pd.DataFrame, persistence_scores: pd.Series,
                    threshold: float, sl_mult: float = 0.5, tp_mult: float = 1.5) -> pd.DataFrame:
    """Replay with persistence-based trade filtering.

    When persistence score is below threshold, override signal to NEUTRAL
    (skip the trade). All accepted trades use fixed geometry (default tight).

    This tests the hypothesis: persistence is a failure detector, not a geometry controller.
    """
    trades = []
    pos = None

    for idx, (timestamp, row) in enumerate(predictions.iterrows()):
        signal = int(row['signal'])
        close = float(row['close'])

        # Get persistence score at this bar
        persist = persistence_scores.get(timestamp, None) if persistence_scores is not None else None

        # Override: filter out low-persistence signals
        if signal in (0, 2) and persist is not None and not np.isnan(persist):
            if persist < threshold:
                signal = 1  # override to NEUTRAL

        # 1. Check existing position for SL/TP hit
        if pos is not None:
            hit = check_barrier_hit(row, pos)
            if hit is not None:
                reason, exit_price = hit
                ret = compute_trade_return(pos.side, pos.entry_price, exit_price)
                trades.append({
                    'entry_time': pos.entry_time,
                    'exit_time': timestamp,
                    'side': pos.side,
                    'entry_price': pos.entry_price,
                    'exit_price': exit_price,
                    'sl_price': pos.sl_price,
                    'tp_price': pos.tp_price,
                    'reason': reason,
                    'hold_bars': idx - pos.entry_idx,
                    'return_pct': ret,
                    'vol_at_entry': pos.vol_at_entry,
                    'conf_at_entry': pos.conf_at_entry,
                    'persistence_at_entry': pos.__dict__.get('persistence_at_entry', None),
                    'year': int(row['year']),
                    'regime': str(row['regime']),
                })
                pos = None

        # 2. Determine desired side
        if signal == 2:
            desired = 'long'
        elif signal == 0:
            desired = 'short'
        else:
            continue

        # 3. Position management (fixed geometry)
        if pos is None:
            vol = float(row.get('volatility', 0.01))
            if pd.isna(vol) or vol <= 0:
                vol = 0.01
            sl = close * (1 - vol * sl_mult) if desired == 'long' else close * (1 + vol * sl_mult)
            tp = close * (1 + vol * tp_mult) if desired == 'long' else close * (1 - vol * tp_mult)
            pos = PositionState(
                side=desired, entry_price=close, entry_time=timestamp,
                sl_price=sl, tp_price=tp,
                vol_at_entry=vol, conf_at_entry=float(row['confidence']),
                entry_idx=idx,
            )
            pos.persistence_at_entry = persist
        elif pos.side != desired:
            ret = compute_trade_return(pos.side, pos.entry_price, close)
            trades.append({
                'entry_time': pos.entry_time,
                'exit_time': timestamp,
                'side': pos.side,
                'entry_price': pos.entry_price,
                'exit_price': close,
                'sl_price': pos.sl_price,
                'tp_price': pos.tp_price,
                'reason': 'flip',
                'hold_bars': idx - pos.entry_idx,
                'return_pct': ret,
                'vol_at_entry': pos.vol_at_entry,
                'conf_at_entry': pos.conf_at_entry,
                'persistence_at_entry': pos.__dict__.get('persistence_at_entry', None),
                'year': int(row['year']),
                'regime': str(row['regime']),
            })
            vol = float(row.get('volatility', 0.01))
            if pd.isna(vol) or vol <= 0:
                vol = 0.01
            sl = close * (1 - vol * sl_mult) if desired == 'long' else close * (1 + vol * sl_mult)
            tp = close * (1 + vol * tp_mult) if desired == 'long' else close * (1 - vol * tp_mult)
            pos = PositionState(
                side=desired, entry_price=close, entry_time=timestamp,
                sl_price=sl, tp_price=tp,
                vol_at_entry=vol, conf_at_entry=float(row['confidence']),
                entry_idx=idx,
            )
            pos.persistence_at_entry = persist

    # Close open position
    if pos is not None:
        last_row = predictions.iloc[-1]
        ret = compute_trade_return(pos.side, pos.entry_price, float(last_row['close']))
        trades.append({
            'entry_time': pos.entry_time,
            'exit_time': predictions.index[-1],
            'side': pos.side,
            'entry_price': pos.entry_price,
            'exit_price': float(last_row['close']),
            'sl_price': pos.sl_price,
            'tp_price': pos.tp_price,
            'reason': 'expiry',
            'hold_bars': len(predictions) - 1 - pos.entry_idx,
            'return_pct': ret,
            'vol_at_entry': pos.vol_at_entry,
            'conf_at_entry': pos.conf_at_entry,
            'persistence_at_entry': pos.__dict__.get('persistence_at_entry', None),
            'year': int(last_row['year']),
            'regime': str(last_row['regime']),
        })

    if not trades:
        return pd.DataFrame(columns=[
            'entry_time', 'exit_time', 'side', 'entry_price', 'exit_price',
            'sl_price', 'tp_price', 'reason', 'hold_bars', 'return_pct',
            'vol_at_entry', 'conf_at_entry', 'persistence_at_entry',
            'year', 'regime',
        ])
    return pd.DataFrame(trades)


def run_filter_experiment(name: str, predictions: pd.DataFrame,
                           persistence_scores: pd.Series = None,
                           force: bool = False) -> dict:
    """Test persistence as a trade filter (not geometry controller).

    Compares:
      - Baseline: tight (no filter)
      - Filter A: remove bottom 10% by persistence
      - Filter B: remove bottom 20% by persistence
      - Filter C: remove bottom 5% by persistence
    """
    out_dir = os.path.join(EXECUTION_DIR, name)
    os.makedirs(out_dir, exist_ok=True)
    result_path = os.path.join(out_dir, 'filter_experiment.json')

    if os.path.exists(result_path) and not force:
        with open(result_path) as f:
            return json.load(f)

    logger.info('=' * 60)
    logger.info('Persistence filter experiment for %s...', name)
    logger.info('=' * 60)

    if persistence_scores is None:
        persistence_scores = compute_persistence_scores(name, predictions)
        if persistence_scores is None:
            return None

    from research.execution_surface.replay_engine import replay, ReplayConfig

    persist_clean = persistence_scores.dropna()
    thresholds = {
        'filter_5pct': float(persist_clean.quantile(0.05)),
        'filter_10pct': float(persist_clean.quantile(0.10)),
        'filter_20pct': float(persist_clean.quantile(0.20)),
    }
    logger.info('  Filter thresholds:  5%%=%.4f  10%%=%.4f  20%%=%.4f',
                thresholds['filter_5pct'], thresholds['filter_10pct'], thresholds['filter_20pct'])

    results = {}
    fixed_config = ReplayConfig(sl_mult=0.5, tp_mult=1.5)

    # Baseline: tight, no filter
    logger.info('  Running baseline (tight, no filter)...')
    trades = replay(predictions, fixed_config)
    metrics = compute_trade_metrics(trades, 0.5, 1.5)
    metrics['filter_label'] = 'none'
    metrics['threshold'] = None
    results['baseline_tight'] = metrics

    # Filtered scenarios
    for flabel, th in sorted(thresholds.items()):
        logger.info('  Running %s (threshold=%.4f)...', flabel, th)
        trades = replay_filtered(predictions, persistence_scores, th)
        metrics = compute_trade_metrics(trades, 0.5, 1.5)
        metrics['filter_label'] = flabel
        metrics['threshold'] = th
        results[flabel] = metrics
        if metrics.get('valid'):
            n_filtered = metrics.get('n_trades', 0)
            n_baseline = results['baseline_tight'].get('n_trades', 0)
            logger.info('    Sharpe=%.4f  PF=%.2f  Win=%.2f%%  Trades=%d (%d filtered out)',
                        metrics.get('sharpe', 0), metrics.get('pf', 0),
                        metrics.get('win_rate', 0) * 100, n_filtered, n_baseline - n_filtered)

    result = {
        'asset': name,
        'n_total_directional': int(predictions['signal'].isin([0, 2]).sum()),
        'persistence_stats': {
            'mean': round(float(persistence_scores.mean()), 4),
            'std': round(float(persistence_scores.std()), 4),
            'q05': round(float(persist_clean.quantile(0.05)), 4),
            'q10': round(float(persist_clean.quantile(0.10)), 4),
            'q20': round(float(persist_clean.quantile(0.20)), 4),
        },
        'thresholds': {k: round(v, 4) for k, v in thresholds.items()},
        'scenarios': results,
    }

    with open(result_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    logger.info('  Saved to %s', result_path)
    return result


def evaluate_dynamic_vs_fixed(name: str, predictions: pd.DataFrame,
                                persistence_scores: pd.Series = None,
                                force: bool = False) -> dict:
    """Compare dynamic persistence-conditioned execution vs fixed medium/loose baselines."""
    out_dir = os.path.join(EXECUTION_DIR, name)
    os.makedirs(out_dir, exist_ok=True)
    result_path = os.path.join(out_dir, 'comparison.json')

    if os.path.exists(result_path) and not force:
        with open(result_path) as f:
            return json.load(f)

    logger.info('=' * 60)
    logger.info('Persistence-conditioned execution for %s...', name)
    logger.info('=' * 60)

    # 1. Compute persistence scores if not provided
    if persistence_scores is None:
        logger.info('  Computing persistence scores...')
        persistence_scores = compute_persistence_scores(name, predictions)
        if persistence_scores is None:
            logger.warning('  %s: cannot compute persistence scores', name)
            return None

    logger.info('  Persistence score stats: mean=%.3f  std=%.3f  q25=%.3f  q75=%.3f',
                persistence_scores.mean(), persistence_scores.std(),
                persistence_scores.quantile(0.25), persistence_scores.quantile(0.75))

    # Compute empirical quantile thresholds for dynamic mapping
    # Use the persistence score distribution to define low/mid/high buckets
    persist_clean = persistence_scores.dropna()
    low_th = float(persist_clean.quantile(0.33))
    mid_th = float(persist_clean.quantile(0.67))
    thresholds = (low_th, mid_th)
    logger.info('  Dynamic thresholds: low<%.4f  mid<%.4f  high>=%.4f',
                low_th, mid_th, mid_th)

    # 2. Run three scenarios
    from research.execution_surface.replay_engine import replay, ReplayConfig

    scenarios = {
        'fixed_medium': ReplayConfig(sl_mult=0.75, tp_mult=2.25),
        'fixed_loose': ReplayConfig(sl_mult=1.0, tp_mult=3.0),
        'fixed_tight': ReplayConfig(sl_mult=0.5, tp_mult=1.5),
    }

    results = {}
    for label, config in scenarios.items():
        logger.info('  Running %s...', label)
        trades = replay(predictions, config)
        metrics = compute_trade_metrics(trades, config.sl_mult, config.tp_mult)
        results[label] = metrics
        if metrics.get('valid'):
            logger.info('    Sharpe=%.4f  PF=%.2f  Win=%.2f%%  Trades=%d',
                        metrics.get('sharpe', 0), metrics.get('pf', 0),
                        metrics.get('win_rate', 0) * 100, metrics.get('n_trades', 0))

    # 3. Run dynamic persistence-conditioned
    logger.info('  Running persistence_dynamic...')
    dynamic_trades = replay_dynamic(predictions, persistence_scores, thresholds)
    dynamic_metrics = compute_trade_metrics(dynamic_trades, 0.75, 2.25)
    # Override sl_mult/tp_mult in metrics to reflect the dynamic range
    dynamic_metrics['sl_mult_range'] = '0.5-1.0'
    dynamic_metrics['tp_mult_range'] = '1.5-3.0'
    results['persistence_dynamic'] = dynamic_metrics
    if dynamic_metrics.get('valid'):
        logger.info('    Sharpe=%.4f  PF=%.2f  Win=%.2f%%  Trades=%d',
                    dynamic_metrics.get('sharpe', 0), dynamic_metrics.get('pf', 0),
                    dynamic_metrics.get('win_rate', 0) * 100, dynamic_metrics.get('n_trades', 0))

    # 4. Analyze dynamic trade outcomes by persistence bucket
    if len(dynamic_trades) > 0 and 'persistence_at_entry' in dynamic_trades.columns:
        dynamic_trades['persistence_bucket'] = pd.cut(
            dynamic_trades['persistence_at_entry'].fillna(0.5),
            bins=[0, 0.33, 0.67, 1.0],
            labels=['low', 'mid', 'high'],
        )
        bucket_analysis = dynamic_trades.groupby('persistence_bucket', observed=True).agg(
            n_trades=('return_pct', 'count'),
            mean_return=('return_pct', 'mean'),
            win_rate=('return_pct', lambda x: (x > 0).mean()),
            mean_hold=('hold_bars', 'mean'),
            mean_sl=('sl_mult_used', 'mean'),
            mean_tp=('tp_mult_used', 'mean'),
        ).to_dict('index')
        results['persistence_bucket_analysis'] = {}
        for bucket, stats in bucket_analysis.items():
            results['persistence_bucket_analysis'][str(bucket)] = {
                k: round(float(v), 4) if isinstance(v, float) else int(v) if isinstance(v, (int, np.integer)) else v
                for k, v in stats.items()
            }

    # Save trades for inspection
    fixed_trades_path = os.path.join(out_dir, 'trades_fixed_medium.parquet')
    replay(predictions, ReplayConfig(sl_mult=0.75, tp_mult=2.25)).to_parquet(fixed_trades_path)
    dynamic_trades_path = os.path.join(out_dir, 'trades_dynamic.parquet')
    dynamic_trades.to_parquet(dynamic_trades_path)

    result = {
        'asset': name,
        'n_persistence_scored_bars': int(persistence_scores.notna().sum()),
        'scenarios': results,
    }

    with open(result_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    logger.info('  Saved to %s', result_path)
    return result


def run_all(force=False):
    """Run persistence-conditioned execution for target assets."""
    from research.execution_surface.replay_engine import replay, ReplayConfig

    # Phase G+ Step 1: filter experiment for GBPUSD, AUDJPY, USDCAD
    targets = ['GBPUSD', 'AUDJPY', 'USDCAD']

    report = {}
    for name in targets:
        oos_path = os.path.join(SANDBOX_BASE, name, 'retrain', 'oos_medium.parquet')
        if not os.path.exists(oos_path):
            logger.warning('%s: no retrained predictions at %s', name, oos_path)
            continue

        predictions = pd.read_parquet(oos_path)
        persist_scores = compute_persistence_scores(name, predictions)
        if persist_scores is None:
            continue

        try:
            result = run_filter_experiment(name, predictions, persist_scores, force=force)
            if result:
                report[name] = result
        except Exception as e:
            logger.error('%s: FAILED — %s', name, e)
            import traceback; traceback.print_exc()

    if not report:
        return report

    # Console summary
    print('\n' + '=' * 130)
    print('PHASE G+ — PERSISTENCE FILTER EXPERIMENT')
    print('=' * 130)

    for name in sorted(report.keys()):
        r = report[name]
        ps = r['persistence_stats']
        print(f'\n{name}:')
        print(f'  Persistence: mean={ps["mean"]:.3f}  q05={ps["q05"]:.3f}  q10={ps["q10"]:.3f}  q20={ps["q20"]:.3f}')
        print(f'  {"Scenario":20s} {"Sharpe":>8s} {"PF":>6s} {"Win Rate":>9s} '
              f'{"Trades":>7s} {"Expect":>8s} {"MaxDD":>8s} {"Filtered":>9s}')
        print('  ' + '-' * 85)

        for scenario, metrics in sorted(r['scenarios'].items()):
            sharpe = f'{metrics["sharpe"]:.4f}' if metrics.get('sharpe') is not None else 'N/A'
            pf = f'{metrics["pf"]:.2f}' if metrics.get('pf') is not None else 'N/A'
            wr = f'{metrics["win_rate"]:.2%}' if metrics.get('win_rate') is not None else 'N/A'
            n = f'{metrics["n_trades"]}' if metrics.get('n_trades') is not None else 'N/A'
            exp = f'{metrics["expectancy"]:.4f}' if metrics.get('expectancy') is not None else 'N/A'
            mdd = f'{metrics["max_dd"]:.4f}' if metrics.get('max_dd') is not None else 'N/A'
            label = metrics.get('filter_label', scenario)
            baseline_n = r['scenarios'].get('baseline_tight', {}).get('n_trades', 0)
            filtered = baseline_n - metrics.get('n_trades', 0) if label != 'none' else 0
            filt_str = f'{filtered}' if filtered > 0 else '-'
            print(f'  {label:20s} {sharpe:>8s} {pf:>6s} {wr:>9s} {n:>7s} '
                  f'{exp:>8s} {mdd:>8s} {filt_str:>9s}')

    print('\n' + '=' * 130)
    print('INTERPRETATION')
    print('=' * 130)
    print()
    print('If filtered scenarios improve Sharpe over baseline:')
    print('  Persistence works as a rare-event failure detector.')
    print('  Low-persistence trades are genuinely lower quality.')
    print()
    print('If Sharpe does not improve but drawdown reduces:')
    print('  Persistence helps with tail risk but not average case.')
    print('  Still useful for risk censoring.')
    print()
    print('If no improvement across any asset:')
    print('  Persistence signal is execution-orthogonal —')
    print('  it predicts signal survival but not trade quality.')
    print()
    print('If GBPUSD improves but AUDJPY/USDCAD do not:')
    print('  Persistence is asset-specific, not a global filter.')
    print('  Deploy per-asset, not portfolio-wide.')
    print()

    return report


if __name__ == '__main__':
    run_all()
