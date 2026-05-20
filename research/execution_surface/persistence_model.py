"""Phase G — Regime Latent Model: Persistence Prediction.

The outcome head failed because MFE/MAE magnitudes are unrecoverable from the
current feature basis. The missing latent variable is *persistence* — how long
a detected regime transition survives before reversing.

Instead of predicting payoff magnitude, predict:
  P(signal survives k bars | feature state)

This is fundamentally different from confidence calibration:
  - Confidence = P(transition happened | features)  [what the classifier does]
  - Persistence = P(transition persists k bars | features, transition detected)

If persistence is predictable from features (while magnitude was not),
that validates the "regime latent" hypothesis — the feature space encodes
transition duration, not transition payoff.

Architecture:
  - Target: for each directional bar, binary survival at k=1..7 bars
  - Model: XGBoost binary classifier per horizon (or multi-horizon joint)
  - Features: same feature space as classifier (rebuilt from scratch)
  - Evaluation: survival curve separation by predicted persistence quintile

Output: data/sandbox/persistence/ — per-asset models + survival curves
         data/sandbox/persistence_report.json — cross-asset comparison
"""

import os, sys, json, logging, pickle
import pandas as pd
import numpy as np
import xgboost as xgb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from features.registry import FEATURE_REGISTRY
from research.execution_surface.replay_engine import replay, ReplayConfig
from research.execution_surface.monte_carlo import compute_trade_metrics, MIN_TRADES

logger = logging.getLogger("quantforge.execution_surface.persistence")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

SANDBOX_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            'data', 'sandbox')
PERSISTENCE_DIR = os.path.join(SANDBOX_BASE, 'persistence')
os.makedirs(PERSISTENCE_DIR, exist_ok=True)

HORIZONS = [1, 2, 3, 4, 5, 6, 7, 10, 15, 20]
TRAIN_SPLIT = 0.6
MODEL_PARAMS = {
    'n_estimators': 300, 'max_depth': 3, 'learning_rate': 0.05,
    'objective': 'binary:logistic',
    'random_state': 42, 'n_jobs': 1, 'tree_method': 'hist', 'verbosity': 0,
}

ASSETS = [
    'USDCHF', 'EURAUD', 'USDCAD',
    'GBPUSD', 'NZDJPY', 'AUDJPY',
    'GBPJPY', 'CADJPY', 'USDJPY',
]


def compute_persistence_targets(predictions: pd.DataFrame, horizons: list = None) -> pd.DataFrame:
    """For each directional bar, compute survival at each horizon.

    Survival = signal has not reversed (0→2 or 2→0) within k bars.
    Neutral (1) transitions are allowed — reversal means active flip.
    """
    if horizons is None:
        horizons = HORIZONS
    signals = predictions['signal'].values.astype(int)
    N = len(signals)

    targets = {}
    for h in horizons:
        survival = np.full(N, np.nan)
        for i in range(N - h):
            sig = signals[i]
            if sig == 1:  # NEUTRAL — skip
                continue
            future = signals[i + 1:i + 1 + h]
            if sig == 2:  # LONG: reversal = any SHORT (0)
                reversed = np.any(future == 0)
            else:  # SHORT: reversal = any LONG (2)
                reversed = np.any(future == 2)
            survival[i] = 0.0 if reversed else 1.0
        targets[f'survive_{h}'] = survival

    return pd.DataFrame(targets, index=predictions.index)


def persistence_one(name: str, predictions: pd.DataFrame, force: bool = False) -> dict:
    """Train and evaluate persistence model for a single asset."""
    out_dir = os.path.join(PERSISTENCE_DIR, name)
    os.makedirs(out_dir, exist_ok=True)

    result_path = os.path.join(out_dir, 'persistence_results.json')
    if os.path.exists(result_path) and not force:
        with open(result_path) as f:
            return json.load(f)

    logger.info('=' * 60)
    logger.info('Persistence model for %s...', name)
    logger.info('=' * 60)

    # 1. Compute persistence targets
    logger.info('  Computing persistence targets (horizons=%s)...', HORIZONS)
    targets = compute_persistence_targets(predictions, HORIZONS)
    directional = (predictions['signal'] != 1).values
    n_directional = directional.sum()
    logger.info('  %d / %d bars with directional signals', n_directional, len(predictions))

    # Log base survival rates
    logger.info('  Base survival rates:')
    for h in HORIZONS:
        col = f'survive_{h}'
        valid = targets[col].dropna()
        if len(valid) > 0:
            logger.info('    k=%2d:  surv=%.1f%%  (n=%d)', h, valid.mean() * 100, len(valid))

    # 2. Build features from scratch
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

    logger.info('  Rebuilding features for persistence model...')
    df = _fetch(ticker, years=15)
    macro_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                              'data', 'processed', 'macro_factors.parquet')
    macro = compute_macro_derived(pd.read_parquet(macro_path))
    ref = _fetch('SPY', years=15) if contract.requires_ref else None
    features_df = build_features(df, macro, ref, contract)

    common_idx = predictions.index.intersection(features_df.index)
    if len(common_idx) < 100:
        logger.warning('  %s: insufficient overlapping index (%d)', name, len(common_idx))
        return None
    predictions_aligned = predictions.loc[common_idx]
    features_aligned = features_df.loc[common_idx]
    targets_aligned = targets.loc[common_idx]
    logger.info('  %d bars with aligned features', len(common_idx))

    feature_names = list(contract.features)
    available = [f for f in feature_names if f in features_aligned.columns]
    if not available:
        logger.warning('  %s: no feature columns available', name)
        return None
    logger.info('  Using %d features', len(available))
    X = features_aligned[available].values
    n_total = len(predictions_aligned)

    # 3. Chronological split
    split_idx = int(n_total * TRAIN_SPLIT)
    train_mask = np.arange(n_total) < split_idx
    eval_mask = np.arange(n_total) >= split_idx

    train_directional = train_mask & directional[:n_total]
    eval_directional = eval_mask & directional[:n_total]

    X_train = X[train_directional]
    X_eval = X[eval_directional]

    logger.info('  Train: %d directional bars', len(X_train))
    logger.info('  Eval:  %d directional bars', len(X_eval))

    if len(X_train) < 50 or len(X_eval) < 20:
        logger.warning('  %s: insufficient training data', name)
        return None

    # 4. Train persistence model for each horizon
    models = {}
    horizon_results = {}
    conf_eval_raw = predictions_aligned['confidence'].values[eval_directional]

    for h in HORIZONS:
        col = f'survive_{h}'
        y_h = targets_aligned[col].values

        y_train = y_h[train_directional]
        y_eval = y_h[eval_directional]

        # Skip horizon if too few valid targets
        valid_train = ~np.isnan(y_train)
        valid_eval = ~np.isnan(y_eval)
        if valid_train.sum() < 50 or valid_eval.sum() < 20:
            logger.info('    k=%2d: insufficient targets (train=%d, eval=%d), skipping',
                        h, valid_train.sum(), valid_eval.sum())
            continue

        X_train_h = X_train[valid_train]
        y_train_h = y_train[valid_train].astype(int)
        X_eval_h = X_eval[valid_eval]
        y_eval_h = y_eval[valid_eval].astype(int)

        model = xgb.XGBClassifier(**MODEL_PARAMS)
        model.fit(X_train_h, y_train_h, verbose=False)

        models[h] = model

        # Predict survival probability
        pred_surv = model.predict_proba(X_eval_h)[:, 1]
        actual_surv = y_eval_h

        # Correlation metrics
        from scipy.stats import pearsonr, spearmanr
        valid_corr = ~(np.isnan(pred_surv) | np.isnan(actual_surv))
        if valid_corr.sum() > 10:
            p_r, p_p = pearsonr(pred_surv[valid_corr], actual_surv[valid_corr])
            s_r, s_p = spearmanr(pred_surv[valid_corr], actual_surv[valid_corr])
        else:
            p_r, p_p = 0.0, 1.0
            s_r, s_p = 0.0, 1.0

        # Compare with raw confidence as baseline
        conf_eval_h = conf_eval_raw[valid_eval[:len(conf_eval_raw)]]

        if len(conf_eval_h) > 10:
            conf_r, _ = pearsonr(conf_eval_h, actual_surv[valid_corr])
        else:
            conf_r = 0.0

        logger.info('    k=%2d:  n=%d  base_surv=%.1f%%  Persistence r=%+.4f  Conf r=%+.4f',
                    h, len(y_eval_h), y_eval_h.mean() * 100, p_r, conf_r)

        # Quintile separation: sort eval by predicted survival
        order = np.argsort(pred_surv)
        n_eval_h = len(order)
        qsize = n_eval_h // 5
        quintiles = {}
        for q in range(5):
            lo = q * qsize
            hi = (q + 1) * qsize if q < 4 else n_eval_h
            idx = order[lo:hi]
            quintiles[f'Q{q + 1}'] = {
                'n': int(len(idx)),
                'pred_surv': round(float(pred_surv[idx].mean()), 4),
                'actual_surv': round(float(actual_surv[idx].mean()), 4),
            }

        horizon_results[h] = {
            'n_eval': int(valid_eval.sum()),
            'base_survival_rate': round(float(y_eval_h.mean()), 4),
            'pearson_r': round(float(p_r), 4),
            'pearson_p': round(float(p_p), 4),
            'spearman_r': round(float(s_r), 4),
            'confidence_vs_survival_pearson': round(float(conf_r), 4),
            'quintiles': quintiles,
        }

    if not models:
        logger.warning('  %s: no horizon models trained', name)
        return None

    # 5. Save models
    model_dir = os.path.join(out_dir, 'models')
    os.makedirs(model_dir, exist_ok=True)
    for h, model in models.items():
        with open(os.path.join(model_dir, f'model_k{h:02d}.pkl'), 'wb') as f:
            pickle.dump(model, f)

    result = {
        'asset': name,
        'features': available,
        'n_train_directional': int(X_train.shape[0]),
        'n_eval_directional': int(X_eval.shape[0]),
        'horizons': {str(h): v for h, v in sorted(horizon_results.items())},
    }

    with open(result_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    logger.info('  Result saved to %s', result_path)
    return result


def run_all(force=False):
    """Run persistence model for all assets."""
    report = {}

    for name in ASSETS:
        oos_path = os.path.join(SANDBOX_BASE, name, 'retrain', 'oos_medium.parquet')
        if not os.path.exists(oos_path):
            logger.warning('%s: no retrained predictions at %s', name, oos_path)
            continue
        predictions = pd.read_parquet(oos_path)
        try:
            result = persistence_one(name, predictions, force=force)
            if result:
                report[name] = result
        except Exception as e:
            logger.error('%s: FAILED — %s', name, e)
            import traceback; traceback.print_exc()

    report_path = os.path.join(PERSISTENCE_DIR, 'persistence_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    # Console summary
    print('\n' + '=' * 130)
    print('PHASE G — PERSISTENCE MODEL RESULTS')
    print('=' * 130)

    for name in sorted(report.keys()):
        r = report[name]
        horizons = r['horizons']
        print(f'\n{name}:')
        print(f'  {"k":>3s}  {"N":>6s}  {"Base Surv":>10s}  {"Pears r":>8s}  {"Spear r":>8s}  {"Conf r":>8s}  {"Q1 Surv":>8s}  {"Q5 Surv":>8s}  {"Spread":>8s}')
        print('  ' + '-' * 90)

        for h_str in sorted(horizons.keys(), key=int):
            h = horizons[h_str]
            q1 = h['quintiles'].get('Q1', {})
            q5 = h['quintiles'].get('Q5', {})
            spread = q5.get('actual_surv', 0) - q1.get('actual_surv', 0)
            print(f'  {int(h_str):>3d}  {h["n_eval"]:>6d}  {h["base_survival_rate"]:>9.1%}  '
                  f'{h["pearson_r"]:>+8.4f}  {h["spearman_r"]:>+8.4f}  {h["confidence_vs_survival_pearson"]:>+8.4f}  '
                  f'{q1.get("actual_surv", 0):>7.1%}  {q5.get("actual_surv", 0):>7.1%}  {spread:>+7.1%}')

    print('\n' + '=' * 130)
    print('INTERPRETATION')
    print('=' * 130)
    print()
    print('If Persistence Pearson r > 0.2:')
    print('  Signal persistence IS predictable from features.')
    print('  Use predicted survival as trade filter: only take signals with high persistence.')
    print()
    print('If Persistence r ≈ Conf r (≈0):')
    print('  Even persistence is not in the feature space.')
    print('  The feature basis is fully exhausted for all signal expansions.')
    print('  Remaining lever is pure execution (geometry + regime segmentation).')
    print()
    print('If persistence separates Q1 vs Q5 actual survival > 20%:')
    print('  Ranking works — can filter trades by persistence score.')
    print()
    print('If base survival rate decays gracefully with k:')
    print('  Typical regime persistence curve — validates the framing.')
    print('  If it crashes (e.g., 80% → 20% between k=1 and k=2):')
    print('  Edge is extremely short-lived, requiring very tight exits.')
    print()

    return report


if __name__ == '__main__':
    run_all()
