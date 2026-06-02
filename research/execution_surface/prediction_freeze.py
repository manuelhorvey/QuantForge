"""Phase A.1 — Freeze OOS predictions via walk-forward.

For each live asset:
1. Fetch price + macro + SPY ref
2. Build features + labels via FeatureContract
3. Walk-forward (5yr train / 1yr test), storing full OHLC bars
4. Store OOS predictions + OHLC + metadata to parquet

Output: data/sandbox/{NAME}/oos_predictions.parquet
"""

import os, sys, logging
import pandas as pd
import numpy as np
import xgboost as xgb
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from features.builder import compute_macro_derived, build_features
from features.registry import FEATURE_REGISTRY

logger = logging.getLogger("quantforge.execution_surface.freeze")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

SANDBOX_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            'data', 'sandbox')
WF_TRAIN_YEARS = 5
MIN_TRAIN_ROWS = 200
MIN_TEST_ROWS = 30
MODEL_PARAMS = {
    'n_estimators': 300, 'max_depth': 2, 'learning_rate': 0.02,
    'objective': 'multi:softprob', 'num_class': 3,
    'random_state': 42, 'n_jobs': 1, 'tree_method': 'hist', 'verbosity': 0,
}


def _normalize(df):
    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize('US/Eastern')
    else:
        df.index = df.index.tz_convert('US/Eastern')
    return df


def fetch_history(ticker, years=15):
    end = pd.Timestamp.now()
    start = f'{end.year - years}-01-01'
    df = yf.download(ticker, start=start, end=end.strftime('%Y-%m-%d'), auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns={'Close': 'close', 'High': 'high', 'Low': 'low', 'Open': 'open', 'Volume': 'volume'})
    return _normalize(df)


def compute_volatility(close, span=100):
    returns = np.log(close / close.shift(1))
    return returns.ewm(span=span).std()


def compute_atr(high, low, close, period=14):
    tr = np.maximum(high - low, np.maximum(
        abs(high - close.shift(1)), abs(low - close.shift(1))
    ))
    return tr.rolling(period).mean()


def classify_vol_regime(close):
    vol = compute_volatility(close)
    recent = vol.dropna().iloc[-min(252, len(vol)):]
    if len(recent) < 20:
        return 'unknown'
    low_thresh = recent.quantile(0.33)
    high_thresh = recent.quantile(0.67)
    latest = recent.iloc[-1]
    if latest <= low_thresh:
        return 'low_vol'
    elif latest >= high_thresh:
        return 'high_vol'
    return 'transition'


def freeze_one(ticker, force=False):
    contract = FEATURE_REGISTRY[ticker]
    name = contract.name
    logger.info('=' * 60)
    logger.info('Freezing predictions for %s (%s)', name, ticker)
    logger.info('=' * 60)

    out_dir = os.path.join(SANDBOX_BASE, name)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, 'oos_predictions.parquet')
    if os.path.exists(out_path) and not force:
        logger.info('%s: predictions already frozen at %s', name, out_path)
        return out_path

    logger.info('  Fetching data...')
    df = fetch_history(ticker)
    logger.info('  %d rows from %s to %s', len(df), df.index[0].date(), df.index[-1].date())

    logger.info('  Loading macro and ref...')
    macro_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                              'data', 'processed', 'macro_factors.parquet')
    macro = compute_macro_derived(pd.read_parquet(macro_path))
    ref = fetch_history('SPY', years=15) if contract.requires_ref else None

    logger.info('  Building features and labels...')
    features_df = build_features(df, macro, ref, contract)
    logger.info('  %d feature rows', len(features_df))

    X = features_df[list(contract.features)]
    y = features_df['label'].astype(int)
    close = df['close'].reindex(X.index).ffill()
    high = df['high'].reindex(X.index).ffill()
    low = df['low'].reindex(X.index).ffill()
    open_ = df['open'].reindex(X.index).ffill()
    volume = df['volume'].reindex(X.index).ffill()
    vol_series = compute_volatility(close)
    atr_series = compute_atr(high, low, close)

    years = sorted(X.index.year.unique())
    test_years = [y for y in years if y >= years[0] + WF_TRAIN_YEARS and y <= pd.Timestamp.now().year]
    if not test_years:
        logger.warning('  %s: no valid test years', name)
        return None

    chunks = []
    for ty in test_years:
        tr_end = ty - 1
        tr_start = tr_end - WF_TRAIN_YEARS + 1
        train_mask = ((X.index >= pd.Timestamp(f'{tr_start}-01-01', tz='US/Eastern'))
                      & (X.index <= pd.Timestamp(f'{tr_end}-12-31', tz='US/Eastern')))
        test_mask = ((X.index >= pd.Timestamp(f'{ty}-01-01', tz='US/Eastern'))
                     & (X.index <= pd.Timestamp(f'{ty}-12-31', tz='US/Eastern')))
        X_train = X[train_mask]
        y_train = y[train_mask]
        X_test = X[test_mask]

        if len(X_train) < MIN_TRAIN_ROWS or len(X_test) < MIN_TEST_ROWS:
            logger.info('  %s %d: insufficient data (train=%d, test=%d), skipping',
                        name, ty, len(X_train), len(X_test))
            continue

        # Skip fold if not all 3 classes (short=0, neutral=1, long=2) are present
        split_idx = int(len(X_train) * 0.8)
        train_classes = set(y_train.iloc[:split_idx].unique())
        if train_classes != {0, 1, 2}:
            logger.info('  %s %d: missing classes %s in training split, skipping',
                        name, ty, {0, 1, 2} - train_classes)
            continue

        model = xgb.XGBClassifier(**MODEL_PARAMS)
        model.fit(
            X_train.iloc[:split_idx], y_train.iloc[:split_idx],
            eval_set=[(X_train.iloc[split_idx:], y_train.iloc[split_idx:])],
            verbose=False,
        )
        proba = model.predict_proba(X_test)
        preds = model.predict(X_test)

        chunk = pd.DataFrame(index=X_test.index)
        chunk['open'] = open_.reindex(X_test.index)
        chunk['high'] = high.reindex(X_test.index)
        chunk['low'] = low.reindex(X_test.index)
        chunk['close'] = close.reindex(X_test.index)
        chunk['volume'] = volume.reindex(X_test.index)
        chunk['signal'] = preds.astype(int)
        chunk['prob_long'] = proba[:, 2]
        chunk['prob_short'] = proba[:, 0]
        chunk['prob_neutral'] = proba[:, 1]
        chunk['confidence'] = proba.max(axis=1) * 100
        chunk['volatility'] = vol_series.reindex(X_test.index)
        chunk['atr'] = atr_series.reindex(X_test.index)
        chunk['year'] = ty
        chunk['regime'] = classify_vol_regime(close.loc[:X_test.index[-1]])

        chunks.append(chunk)
        logger.info('  %s %d: %d predictions (%d L / %d S / %d H)',
                    name, ty, len(X_test),
                    int((preds == 2).sum()), int((preds == 0).sum()), int((preds == 1).sum()))

    if not chunks:
        logger.warning('  %s: no OOS predictions generated', name)
        return None

    result = pd.concat(chunks).sort_index()
    result.to_parquet(out_path)
    logger.info('  %s: saved %d OOS predictions to %s', name, len(result), out_path)
    return out_path


def freeze_all(target_tickers=None, force=False):
    tickers = target_tickers or list(FEATURE_REGISTRY.keys())
    results = {}
    for ticker in tickers:
        try:
            path = freeze_one(ticker, force=force)
            if path:
                results[ticker] = path
        except Exception as e:
            logger.error('%s: FAILED — %s', ticker, e)
            import traceback; traceback.print_exc()
    logger.info('Frozen %d/%d assets', len(results), len(tickers))
    return results


if __name__ == '__main__':
    freeze_all()
