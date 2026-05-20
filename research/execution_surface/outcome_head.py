"""Phase E — Outcome Head: predict trade geometry from feature state.

Trains a second model (XGBoost regressor) on the same features as the classifier,
but with regression targets: expected MFE, MAE, and trade duration.

This separates the task of regime transition detection (classifier) from
payoff geometry estimation (outcome head).

Architecture:
  Layer 1 (existing): Classifier — detects regime transitions (LONG/SHORT/NEUTRAL)
  Layer 2 (new):      Outcome Head — predicts E[MFE], E[MAE], E[duration] | state, direction

Usage:
  expected_edge = E[MFE] - E[MAE]
  Can be used for: trade sizing, confidence-weighted exits, regime-aware stops
"""

import os, sys, json, logging, pickle
import pandas as pd
import numpy as np
import xgboost as xgb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from features.registry import FEATURE_REGISTRY
from research.execution_surface.replay_engine import replay, ReplayConfig
from research.execution_surface.monte_carlo import compute_trade_metrics, MIN_TRADES

logger = logging.getLogger("quantforge.execution_surface.outcome_head")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

SANDBOX_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            'data', 'sandbox')
OUTCOME_DIR = os.path.join(SANDBOX_BASE, 'outcome_head')
os.makedirs(OUTCOME_DIR, exist_ok=True)

ASSETS = ['NZDJPY', 'EURAUD', 'USDJPY', 'CADJPY', 'USDCAD', 'AUDJPY']
HORIZON = 20  # tb20-equivalent forward horizon for excursion computation
TRAIN_SPLIT = 0.6  # first 60% of OOS period for training outcome head
MODEL_PARAMS = {
    'n_estimators': 300, 'max_depth': 3, 'learning_rate': 0.05,
    'random_state': 42, 'n_jobs': 1, 'tree_method': 'hist', 'verbosity': 0,
}


def compute_forward_excursion(predictions: pd.DataFrame, horizon: int = HORIZON) -> pd.DataFrame:
    """For each bar with a directional signal, compute forward MFE and MAE.

    Returns DataFrame with columns:
      signal, mfe_pct, mae_pct, mfe_bar, mae_bar, direction
    """
    N = len(predictions)
    signals = predictions['signal'].values.astype(int)
    close = predictions['close'].values
    high = predictions['high'].values
    low = predictions['low'].values

    mfe = np.full(N, np.nan)
    mae = np.full(N, np.nan)
    mfe_bar = np.full(N, -1, dtype=int)
    mae_bar = np.full(N, -1, dtype=int)

    for i in range(N - 1):
        sig = signals[i]
        if sig == 1:  # NEUTRAL — skip
            continue

        end = min(i + 1 + horizon, N)
        future_high = high[i + 1:end]
        future_low = low[i + 1:end]
        entry = close[i]

        if sig == 2:  # LONG
            max_high = future_high.max()
            min_low = future_low.min()
            mfe_val = (max_high / entry - 1) * 100
            mae_val = (min_low / entry - 1) * 100
        else:  # SHORT
            max_low = future_low.min()
            min_high = future_high.min()
            mfe_val = (entry / max_low - 1) * 100 if max_low > 0 else 0
            mae_val = (entry / min_high - 1) * 100 if min_high > 0 else 0

        mfe[i] = mfe_val
        mae[i] = mae_val

        # Bar at which extreme was reached
        if sig == 2:
            mfe_bar[i] = int(np.argmax(future_high))
            mae_bar[i] = int(np.argmin(future_low))
        else:
            mfe_bar[i] = int(np.argmax(entry / future_low))
            mae_bar[i] = int(np.argmin(entry / future_high))

    return pd.DataFrame({
        'signal': signals,
        'mfe_pct': mfe,
        'mae_pct': mae,
        'mfe_bar': mfe_bar,
        'mae_bar': mae_bar,
    }, index=predictions.index)


def outcome_head_one(name: str, predictions: pd.DataFrame, force: bool = False) -> dict:
    """Train and evaluate outcome head for a single asset."""
    out_dir = os.path.join(OUTCOME_DIR, name)
    os.makedirs(out_dir, exist_ok=True)
    model_path = os.path.join(out_dir, 'outcome_model.pkl')
    result_path = os.path.join(out_dir, 'outcome_results.json')

    if os.path.exists(result_path) and not force:
        with open(result_path) as f:
            return json.load(f)

    logger.info('=' * 60)
    logger.info('Outcome head for %s...', name)
    logger.info('=' * 60)

    # 1. Compute forward excursion targets
    logger.info('  Computing forward excursion targets (horizon=%d)...', HORIZON)
    targets = compute_forward_excursion(predictions, HORIZON)
    directional = (targets['signal'] != 1)
    n_directional = directional.sum()
    logger.info('  %d / %d bars have directional signals', n_directional, len(predictions))

    target_mfe = targets['mfe_pct'].values
    target_mae = targets['mae_pct'].values
    target_edge = target_mfe - abs(target_mae)

    # 2. Build features from scratch (predictions only have OHLC + signals, not features)
    ticker_map = {c.name: t for t, c in FEATURE_REGISTRY.items()}
    ticker = ticker_map.get(name)
    if ticker is None:
        logger.warning('  %s: ticker not found', name)
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

    logger.info('  Rebuilding features for outcome head...')
    df = _fetch(ticker, years=15)
    macro_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                              'data', 'processed', 'macro_factors.parquet')
    macro = compute_macro_derived(pd.read_parquet(macro_path))
    ref = _fetch('SPY', years=15) if contract.requires_ref else None
    features_df = build_features(df, macro, ref, contract)

    # Align features with predictions index
    common_idx = predictions.index.intersection(features_df.index)
    if len(common_idx) < 100:
        logger.warning('  %s: insufficient overlapping index (%d)', name, len(common_idx))
        return None
    predictions = predictions.loc[common_idx]
    features_aligned = features_df.loc[common_idx]
    logger.info('  %d bars with aligned features', len(common_idx))

    feature_names = list(contract.features)
    available = [f for f in feature_names if f in features_aligned.columns]
    if not available:
        logger.warning('  %s: no feature columns available', name)
        return None
    logger.info('  Using %d features', len(available))

    X = features_aligned[available].values
    n_total = len(predictions)

    # 3. Chronological split
    split_idx = int(n_total * TRAIN_SPLIT)

    train_mask = np.arange(n_total) < split_idx
    eval_mask = np.arange(n_total) >= split_idx

    # Only train on directional signals
    train_directional = train_mask & directional
    eval_directional = eval_mask & directional

    X_train = X[train_directional]
    y_mfe_train = target_mfe[train_directional]
    y_mae_train = target_mae[train_directional]
    y_edge_train = target_edge[train_directional]

    X_eval = X[eval_directional]
    y_mfe_eval = target_mfe[eval_directional]
    y_mae_eval = target_mae[eval_directional]
    y_edge_eval = target_edge[eval_directional]

    logger.info('  Train: %d directional bars', len(X_train))
    logger.info('  Eval:  %d directional bars', len(X_eval))

    if len(X_train) < 50 or len(X_eval) < 20:
        logger.warning('  %s: insufficient training data', name)
        return None

    # 4. Train regressor for MFE
    logger.info('  Training MFE model...')
    model_mfe = xgb.XGBRegressor(**MODEL_PARAMS)
    model_mfe.fit(X_train, y_mfe_train, verbose=False)

    # 5. Train regressor for MAE (absolute value — predict magnitude of adverse excursion)
    logger.info('  Training MAE model...')
    model_mae = xgb.XGBRegressor(**MODEL_PARAMS)
    model_mae.fit(X_train, abs(y_mae_train), verbose=False)

    # 6. Predict on evaluation set
    pred_mfe = model_mfe.predict(X_eval)
    pred_mae_abs = model_mae.predict(X_eval)
    pred_edge = pred_mfe - pred_mae_abs

    # 7. Evaluate: does predicted edge correlate with actual edge?
    actual_mfe = y_mfe_eval
    actual_mae = y_mae_eval
    actual_edge = y_edge_eval
    actual_edge_abs = actual_mfe - abs(actual_mae)

    # Correlation metrics
    from scipy.stats import pearsonr, spearmanr
    valid = ~(np.isnan(pred_edge) | np.isnan(actual_edge_abs))
    if valid.sum() > 10:
        pearson_r, pearson_p = pearsonr(pred_edge[valid], actual_edge_abs[valid])
        spearman_r, spearman_p = spearmanr(pred_edge[valid], actual_edge_abs[valid])
    else:
        pearson_r, pearson_p = 0.0, 1.0
        spearman_r, spearman_p = 0.0, 1.0

    # Compare with classifier's confidence as benchmark: does confidence correlate with edge?
    conf_eval = predictions['confidence'].values[eval_directional]
    valid_conf = ~(np.isnan(conf_eval) | np.isnan(actual_edge_abs[:len(conf_eval)]))
    if valid_conf.sum() > 10:
        conf_r, conf_p = pearsonr(conf_eval[valid_conf], actual_edge_abs[:len(conf_eval)][valid_conf])
    else:
        conf_r, conf_p = 0.0, 1.0

    logger.info('  Outcome Head:  Pearson r=%.4f (p=%.4f)  Spearman r=%.4f (p=%.4f)',
                pearson_r, pearson_p, spearman_r, spearman_p)
    logger.info('  Classifier confidence vs edge: Pearson r=%.4f (p=%.4f)', conf_r, conf_p)

    # 8. Bucket evaluation: sort eval set by predicted edge, bin into quintiles
    order = np.argsort(pred_edge)
    n_eval = len(order)
    quintile_size = n_eval // 5
    quintile_results = {}
    for q in range(5):
        lo = q * quintile_size
        hi = (q + 1) * quintile_size if q < 4 else n_eval
        idx = order[lo:hi]
        q_actual_edge = actual_edge_abs[idx]
        q_pred_edge = pred_edge[idx]
        q_actual_mfe = actual_mfe[idx]
        q_actual_mae = actual_mae[idx]
        q_pred_mfe = pred_mfe[idx]
        q_pred_mae = pred_mae_abs[idx]

        quintile_results[f'Q{q + 1}'] = {
            'n': int(len(idx)),
            'pred_edge': round(float(np.mean(q_pred_edge)), 4),
            'actual_edge': round(float(np.mean(q_actual_edge)), 4),
            'actual_mfe': round(float(np.mean(q_actual_mfe)), 4),
            'actual_mae': round(float(np.mean(q_actual_mae)), 4),
            'pred_mfe': round(float(np.mean(q_pred_mfe)), 4),
            'pred_mae': round(float(np.mean(q_pred_mae)), 4),
            'win_rate': round(float((q_actual_edge > 0).mean()), 4),
        }

    # Also bucket by classifier confidence for comparison
    conf_order = np.argsort(conf_eval)
    conf_quintile = {}
    for q in range(5):
        lo = q * quintile_size
        hi = (q + 1) * quintile_size if q < 4 else n_eval
        idx = conf_order[lo:hi]
        q_actual_edge = actual_edge_abs[idx]
        q_conf = conf_eval[idx]
        conf_quintile[f'Q{q + 1}'] = {
            'n': int(len(idx)),
            'mean_confidence': round(float(np.mean(q_conf)), 2),
            'actual_edge': round(float(np.mean(q_actual_edge)), 4),
            'win_rate': round(float((q_actual_edge > 0).mean()), 4),
        }

    # Save models
    with open(model_path.replace('.pkl', '_mfe.pkl'), 'wb') as f:
        pickle.dump(model_mfe, f)
    with open(model_path.replace('.pkl', '_mae.pkl'), 'wb') as f:
        pickle.dump(model_mae, f)

    result = {
        'asset': name,
        'n_train': int(len(X_train)),
        'n_eval': int(len(X_eval)),
        'features': available,
        'evaluation': {
            'pearson_r': round(float(pearson_r), 4),
            'pearson_p': round(float(pearson_p), 4),
            'spearman_r': round(float(spearman_r), 4),
            'spearman_p': round(float(spearman_p), 4),
            'confidence_vs_edge_pearson': round(float(conf_r), 4),
        },
        'quintiles_by_predicted_edge': quintile_results,
        'quintiles_by_confidence': conf_quintile,
    }

    with open(result_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    logger.info('  Result saved to %s', result_path)
    return result


def run_all(force=False):
    """Run outcome head for all target assets."""
    report = {}

    for name in ASSETS:
        oos_path = os.path.join(SANDBOX_BASE, name, 'retrain', 'oos_medium.parquet')
        if not os.path.exists(oos_path):
            logger.warning('%s: no retrained predictions at %s', name, oos_path)
            continue
        predictions = pd.read_parquet(oos_path)
        try:
            result = outcome_head_one(name, predictions, force=force)
            if result:
                report[name] = result
        except Exception as e:
            logger.error('%s: FAILED — %s', name, e)
            import traceback; traceback.print_exc()

    # Save report
    report_path = os.path.join(OUTCOME_DIR, 'outcome_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    # Console summary
    print('\n' + '=' * 130)
    print('PHASE E — OUTCOME HEAD RESULTS')
    print('=' * 130)
    print(f'\n{"Asset":12s} {"N train":>8s} {"N eval":>8s} {"Pearson r":>10s} '
          f'{"Spearman r":>11s} {"Conf r":>8s} {"Best Q5 edge":>13s} {"Best Q5 WR":>11s}')
    print('-' * 130)

    for name in sorted(report.keys()):
        r = report[name]
        ev = r['evaluation']
        q5 = r['quintiles_by_predicted_edge'].get('Q5', {})
        q1 = r['quintiles_by_predicted_edge'].get('Q1', {})
        print(f'{name:12s} {r["n_train"]:>8d} {r["n_eval"]:>8d} '
              f'{ev["pearson_r"]:>+10.4f} {ev["spearman_r"]:>+11.4f} '
              f'{ev["confidence_vs_edge_pearson"]:>+8.4f} '
              f'{q5.get("actual_edge", 0):>+13.4f} {q5.get("win_rate", 0):>10.2%}')

    print('\n--- QUINTILE COMPARISON: PREDICTED EDGE vs CLASSIFIER CONFIDENCE ---')
    for name in sorted(report.keys()):
        r = report[name]
        print(f'\n{name}:')
        print(f'  {"Bucket":8s} {"Outcome Head":>30s} {"Classifier Confidence":>30s}')
        print(f'  {"":8s} {"Pred Edge":>9s} {"Act Edge":>9s} {"WR":>7s}   '
              f'{"Conf":>7s} {"Act Edge":>9s} {"WR":>7s}')
        print(f'  {"-"*68}')
        for q in ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']:
            oh = r['quintiles_by_predicted_edge'].get(q, {})
            cc = r['quintiles_by_confidence'].get(q, {})
            if not oh:
                continue
            print(f'  {q:8s} {oh.get("pred_edge", 0):>+9.4f} {oh.get("actual_edge", 0):>+9.4f} '
                  f'{oh.get("win_rate", 0):>6.0%}   '
                  f'{cc.get("mean_confidence", 0):>7.2f} {cc.get("actual_edge", 0):>+9.4f} '
                  f'{cc.get("win_rate", 0):>6.0%}')

    print('\n' + '=' * 130)
    print('INTERPRETATION')
    print('=' * 130)
    print()
    print('If Outcome Head Pearson/Spearman r > 0.2:')
    print('  The regressor captures meaningful payoff geometry from features.')
    print('  expected_edge = E[MFE] - E[MAE] can rank trade quality.')
    print()
    print('If Outcome Head r ≈ confidence r:')
    print('  No improvement over raw classifier confidence — features lack')
    print('  excursion signal separate from classification signal.')
    print()
    print('If Outcome Head r > confidence r * 2:')
    print('  Clear victory — the regressor discovers payoff geometry the')
    print('  classifier cannot express. This validates the two-layer architecture.')
    print()
    print('If best quintile edge is positive while worst is negative:')
    print('  Ranking works — outcome head can be used for dynamic sizing.')
    print()

    return report


if __name__ == '__main__':
    run_all()
