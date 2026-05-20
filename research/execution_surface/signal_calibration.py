"""Phase D — Signal Probability Calibration Layer.

XGBoost raw probabilities are uncalibrated — confidence does not equal expected
correctness. Common in tree ensembles where margin-based confidence dominates.

Protocol:
  1. For each retrained OOS prediction set (medium geometry):
     - Compute forward returns at N horizons (1, 2, 5 bars)
     - Check directional correctness of each prediction
     - Bucket by raw confidence: actual win rate vs stated probability
  2. Fit isotonic regression on (raw_confidence, correctness) per asset
  3. Apply calibration to OOS predictions
  4. Compare: reliability diagrams, ECE, win-rate rank ordering
  5. Evaluate whether calibrated confidence improves replay metrics via
     confidence-conditioned exit timing or trade filtering.

Output: data/sandbox/calibration/ — per-asset calibration models + metrics
         data/sandbox/calibration_report.json — cross-asset summary
"""

import os, sys, json, logging, pickle
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from features.registry import FEATURE_REGISTRY
from research.execution_surface.replay_engine import replay, ReplayConfig
from research.execution_surface.monte_carlo import compute_trade_metrics, MIN_TRADES

logger = logging.getLogger("quantforge.execution_surface.calibration")
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

SANDBOX_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            'data', 'sandbox')
CALIBRATION_DIR = os.path.join(SANDBOX_BASE, 'calibration')
os.makedirs(CALIBRATION_DIR, exist_ok=True)

ASSETS = ['NZDJPY', 'EURAUD', 'USDJPY', 'CADJPY', 'USDCAD', 'AUDJPY']
N_BINS = 10
CALIBRATION_SPLIT = 0.5  # first 50% of OOS period for fitting, last 50% for evaluating


def compute_correctness(predictions: pd.DataFrame, forward_horizon: int = 1) -> pd.Series:
    """Compute directional correctness: was the predicted direction right N bars later?"""
    preds = predictions.copy()
    future_close = preds['close'].shift(-forward_horizon)
    price_change = (future_close / preds['close'] - 1)
    signal = preds['signal'].astype(int)

    correct = pd.Series(False, index=preds.index)
    correct = correct.where(signal != 1, True)  # NEUTRAL is neither right nor wrong

    long_correct = (signal == 2) & (price_change > 0)
    short_correct = (signal == 0) & (price_change < 0)
    correct = long_correct | short_correct

    return correct


def compute_ece(bin_edges, bin_counts, bin_accuracies, bin_confidences):
    """Expected Calibration Error — weighted average of |accuracy - confidence|."""
    total = bin_counts.sum()
    if total == 0:
        return 1.0
    ece = np.sum(bin_counts * np.abs(bin_accuracies - bin_confidences)) / total
    return float(ece)


def reliability_curve(confidences, correct, n_bins=N_BINS):
    """Compute reliability curve: binned confidence vs actual accuracy."""
    bins = np.linspace(0, 1, n_bins + 1)
    bin_centers = (bins[:-1] + bins[1:]) / 2
    bin_accuracies = np.zeros(n_bins)
    bin_confidences = np.zeros(n_bins)
    bin_counts = np.zeros(n_bins)

    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (confidences >= lo) & ((confidences < hi) | (i == n_bins - 1))
        count = mask.sum()
        bin_counts[i] = count
        if count > 0:
            bin_accuracies[i] = correct[mask].mean()
            bin_confidences[i] = confidences[mask].mean()

    ece = compute_ece(bins, bin_counts, bin_accuracies, bin_confidences)

    return {
        'bin_edges': bins.tolist(),
        'bin_centers': bin_centers.tolist(),
        'bin_accuracies': bin_accuracies.tolist(),
        'bin_confidences': bin_confidences.tolist(),
        'bin_counts': bin_counts.astype(int).tolist(),
        'ece': ece,
    }


def fit_isotonic(confidences, correct):
    """Fit isotonic regression: monotonic mapping from raw confidence → calibrated probability."""
    from sklearn.isotonic import IsotonicRegression
    # Only use predictions where we have a signal (not NEUTRAL)
    valid = ~np.isnan(confidences)
    ir = IsotonicRegression(y_min=0.0, y_max=1.0, increasing=True)
    ir.fit(confidences[valid], correct[valid].astype(float))
    return ir


def calibrate_one(name: str, predictions: pd.DataFrame, force: bool = False) -> dict:
    """Run calibration for a single asset's medium-geometry OOS predictions."""
    out_dir = os.path.join(CALIBRATION_DIR, name)
    os.makedirs(out_dir, exist_ok=True)
    model_path = os.path.join(out_dir, 'isotonic.pkl')
    result_path = os.path.join(out_dir, 'calibration.json')

    if os.path.exists(result_path) and not force:
        with open(result_path) as f:
            return json.load(f)

    logger.info('=' * 60)
    logger.info('Calibrating %s...', name)
    logger.info('=' * 60)

    # Compute correctness at multiple horizons
    horizons = [1, 2, 5]
    reliability = {}
    for h in horizons:
        correct = compute_correctness(predictions, h)
        conf = predictions['confidence'] / 100.0  # scale to [0, 1]
        reliability[f'h={h}'] = reliability_curve(conf.values, correct.values)

    # Use horizon=1 for calibration (most responsive)
    correct_1 = compute_correctness(predictions, forward_horizon=1)
    conf_raw = predictions['confidence'] / 100.0

    # Split into calibration fit set and evaluation set (chronological)
    split_idx = int(len(predictions) * CALIBRATION_SPLIT)
    fit_conf = conf_raw.iloc[:split_idx]
    fit_correct = correct_1.iloc[:split_idx]
    eval_conf = conf_raw.iloc[split_idx:]
    eval_correct = correct_1.iloc[split_idx:]

    # Fit isotonic regression on the first half
    logger.info('  Fitting isotonic regression on %d calibration samples...', split_idx)
    ir = fit_isotonic(fit_conf.values, fit_correct.values)
    with open(model_path, 'wb') as f:
        pickle.dump(ir, f)

    # Apply to evaluation set
    eval_calibrated = ir.transform(eval_conf.values)
    eval_calibrated = np.clip(eval_calibrated, 0, 1)

    # Reliability curves for raw vs calibrated on evaluation set
    raw_eval_rel = reliability_curve(eval_conf.values, eval_correct.values)
    cal_eval_rel = reliability_curve(eval_calibrated, eval_correct.values)

    # Win rate by confidence bucket — raw
    raw_conf_buckets = {}
    thresholds = [(0.5, 0.55), (0.55, 0.60), (0.60, 0.70), (0.70, 0.80), (0.80, 1.0)]
    for lo, hi in thresholds:
        mask = (eval_conf >= lo) & (eval_conf < hi)
        n = mask.sum()
        if n >= 5:
            wr = eval_correct[mask].mean()
        else:
            wr = None
        raw_conf_buckets[f'{lo:.2f}-{hi:.2f}'] = {'n': int(n), 'win_rate': round(float(wr), 4) if wr is not None else None}

    # Win rate by calibrated confidence bucket
    cal_conf_buckets = {}
    for lo, hi in thresholds:
        mask = (eval_calibrated >= lo) & (eval_calibrated < hi)
        n = mask.sum()
        if n >= 5:
            wr = eval_correct[mask].mean()
        else:
            wr = None
        cal_conf_buckets[f'{lo:.2f}-{hi:.2f}'] = {'n': int(n), 'win_rate': round(float(wr), 4) if wr is not None else None}

    # Summarize
    result = {
        'asset': name,
        'n_predictions': len(predictions),
        'n_calibration_fit': split_idx,
        'n_calibration_eval': len(predictions) - split_idx,
        'n_long': int((predictions['signal'] == 2).sum()),
        'n_short': int((predictions['signal'] == 0).sum()),
        'n_neutral': int((predictions['signal'] == 1).sum()),
        'reliability_raw': {k: {'ece': round(v['ece'], 4)} for k, v in reliability.items()},
        'reliability_by_horizon': reliability,
        'evaluation': {
            'raw': {'ece': round(raw_eval_rel['ece'], 4), 'buckets': raw_conf_buckets},
            'calibrated': {'ece': round(cal_eval_rel['ece'], 4), 'buckets': cal_conf_buckets},
        },
        'calibration_model': model_path,
    }

    with open(result_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    logger.info('  Raw ECE=%.4f  Calibrated ECE=%.4f',
                raw_eval_rel['ece'], cal_eval_rel['ece'])
    logger.info('  Result saved to %s', result_path)

    return result


def evaluate_calibrated_replay(name: str, predictions: pd.DataFrame, force: bool = False) -> dict:
    """Replay with calibrated confidence vs raw confidence to test whether
    calibrated probabilities improve trade outcomes via confidence-conditioned exits."""
    model_path = os.path.join(CALIBRATION_DIR, name, 'isotonic.pkl')
    if not os.path.exists(model_path):
        return {}

    with open(model_path, 'rb') as f:
        ir = pickle.load(f)

    result = {}
    for label, conf_col in [('raw', 'confidence'), ('calibrated', 'calibrated_confidence')]:
        conf = predictions[conf_col] if conf_col in predictions else predictions['confidence'] / 100.0
        if conf_col not in predictions:
            conf = ir.transform(predictions['confidence'].values / 100.0)
            predictions = predictions.copy()
            predictions['calibrated_confidence'] = np.clip(conf, 0, 1) * 100
            conf = predictions['calibrated_confidence']

        # Replay at medium geometry with all signals
        config = ReplayConfig(sl_mult=0.75, tp_mult=2.25)
        trades = replay(predictions, config)
        metrics = compute_trade_metrics(trades, 0.75, 2.25)

        # Also replay with confidence filter: skip trades below threshold
        for threshold in [0, 50, 60, 70]:
            filtered = predictions[predictions[conf_col if conf_col in predictions else 'confidence'] >= threshold]
            if len(filtered) < 50:
                continue
            trades_f = replay(filtered, config)
            metrics_f = compute_trade_metrics(trades_f, 0.75, 2.25)
            result[f'{label}_filter_{threshold}'] = {
                'n_signals': len(filtered),
                'n_trades': metrics_f.get('n_trades', 0),
                'valid': metrics_f.get('valid', False),
                'sharpe': round(float(metrics_f.get('sharpe', 0)), 4) if metrics_f.get('sharpe') else None,
                'pf': round(float(metrics_f.get('pf', 0)), 4) if metrics_f.get('pf') else None,
                'win_rate': round(float(metrics_f.get('win_rate', 0)), 4) if metrics_f.get('win_rate') else None,
            }

    return result


def run_all(force=False):
    """Run calibration for all target assets."""
    report = {}

    for name in ASSETS:
        oos_path = os.path.join(SANDBOX_BASE, name, 'retrain', 'oos_medium.parquet')
        if not os.path.exists(oos_path):
            logger.warning('%s: no retrained predictions at %s', name, oos_path)
            continue
        predictions = pd.read_parquet(oos_path)

        try:
            cal_result = calibrate_one(name, predictions, force=force)
            report[name] = cal_result
        except Exception as e:
            logger.error('%s: calibration FAILED — %s', name, e)
            import traceback; traceback.print_exc()

    # Save cross-asset report
    report_path = os.path.join(CALIBRATION_DIR, 'calibration_report.json')
    with open(report_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)

    # Console summary
    print('\n' + '=' * 120)
    print('PHASE D — SIGNAL CALIBRATION ANALYSIS')
    print('=' * 120)
    print(f'\n{"Asset":12s} {"N Preds":>8s} {"Raw ECE":>8s} {"Cal ECE":>8s} '
          f'{"1h ECE":>7s} {"2h ECE":>7s} {"5h ECE":>7s}')
    print('-' * 120)
    for name in sorted(report.keys()):
        r = report[name]
        eval_data = r.get('evaluation', {})
        raw_ece = eval_data.get('raw', {}).get('ece', 'N/A')
        cal_ece = eval_data.get('calibrated', {}).get('ece', 'N/A')
        r1 = r.get('reliability_raw', {}).get('h=1', {}).get('ece', 'N/A')
        r2 = r.get('reliability_raw', {}).get('h=2', {}).get('ece', 'N/A')
        r5 = r.get('reliability_raw', {}).get('h=5', {}).get('ece', 'N/A')
        print(f'{name:12s} {r["n_predictions"]:>8d} '
              f'{raw_ece if isinstance(raw_ece, str) else f"{raw_ece:.4f}":>8s} '
              f'{cal_ece if isinstance(cal_ece, str) else f"{cal_ece:.4f}":>8s} '
              f'{r1 if isinstance(r1, str) else f"{r1:.4f}":>7s} '
              f'{r2 if isinstance(r2, str) else f"{r2:.4f}":>7s} '
              f'{r5 if isinstance(r5, str) else f"{r5:.4f}":>7s}')

    print('\n--- WIN RATE BY CONFIDENCE BUCKET (EVALUATION SET) ---')
    for name in sorted(report.keys()):
        r = report[name]
        eval_data = r.get('evaluation', {})
        raw_buckets = eval_data.get('raw', {}).get('buckets', {})
        cal_buckets = eval_data.get('calibrated', {}).get('buckets', {})
        print(f'\n{name}:')
        print(f'  {"Bucket":12s} {"Raw n":>6s} {"Raw WR":>8s} {"Cal n":>6s} {"Cal WR":>8s}')
        for bucket in sorted(raw_buckets.keys()):
            rb = raw_buckets.get(bucket, {})
            cb = cal_buckets.get(bucket, {})
            raw_wr = f'{rb["win_rate"]:.2%}' if rb.get('win_rate') is not None else 'N/A'
            cal_wr = f'{cb["win_rate"]:.2%}' if cb.get('win_rate') is not None else 'N/A'
            print(f'  {bucket:12s} {rb.get("n", 0):>6d} {raw_wr:>8s} '
                  f'{cb.get("n", 0):>6d} {cal_wr:>8s}')

    print('\n' + '=' * 120)
    print('INTERPRETATION')
    print('=' * 120)
    print()
    print('ECE < 0.05: well-calibrated — confidence ≈ actual win rate')
    print('ECE 0.05-0.10: moderately miscalibrated')
    print('ECE > 0.10: severely miscalibrated — confidence is unreliable')
    print()
    print('If calibration succeeds (ECE improves):')
    print('  - confidence can be used for position sizing')
    print('  - confidence-conditioned exits become viable')
    print('  - portfolio-level edge weighting improves')
    print()
    print('If calibration fails (ECE stays high):')
    print('  - the model architecture itself needs reform (Platt, beta, etc.)')
    print('  - or the feature set lacks signal for uncertainty estimation')
    print()

    return report


if __name__ == '__main__':
    run_all()
