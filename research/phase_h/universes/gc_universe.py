"""GC universe — data loading and feature building for macro drift regime.

GC uses the existing FeatureContract at FEATURE_REGISTRY["GC=F"]
with long-horizon forward return labels instead of standard fwd60.
"""

import os, sys, logging
import pandas as pd
import numpy as np
import yfinance as yf

logger = logging.getLogger("quantforge.phase_h.gc_universe")

TICKER = "GC=F"
NAME = "GC"


def _normalize(df):
    df = df.copy()
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    if df.index.tz is None:
        df.index = df.index.tz_localize('US/Eastern')
    else:
        df.index = df.index.tz_convert('US/Eastern')
    return df


def fetch_data(years=15):
    """Fetch GC data with OHLCV."""
    end = pd.Timestamp.now()
    start = f'{end.year - years}-01-01'
    df = yf.download(TICKER, start=start, end=end.strftime('%Y-%m-%d'), auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(columns={'Close': 'close', 'High': 'high', 'Low': 'low', 'Open': 'open', 'Volume': 'volume'})
    return _normalize(df)


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


def build_gc_features():
    """Build features for GC using the existing FeatureContract.

    Returns:
        (features_df, raw_df, available_features) tuple
    """
    sys.path.insert(0, PROJECT_ROOT)
    from features.registry import FEATURE_REGISTRY
    from features.builder import compute_macro_derived, build_features

    contract = FEATURE_REGISTRY[TICKER]
    feature_names = list(contract.features)

    logger.info('  GC: fetching data...')
    df = fetch_data(years=15)
    logger.info('  GC: %d rows', len(df))

    macro_path = os.path.join(PROJECT_ROOT, 'data', 'processed', 'macro_factors.parquet')
    macro = compute_macro_derived(pd.read_parquet(macro_path))

    logger.info('  GC: building features...')
    features_df = build_features(df, macro, ref=None, contract=contract)
    logger.info('  GC: %d feature rows', len(features_df))

    available = [f for f in feature_names if f in features_df.columns]
    logger.info('  GC: %d / %d features available', len(available), len(feature_names))

    return features_df, df, available


def create_prediction_frame(df, signal, confidence, name='gc'):
    """Create a prediction DataFrame with OHLC + signal + confidence matching replay format."""
    result = df[['open', 'high', 'low', 'close', 'volume']].copy()
    result['signal'] = signal
    result['confidence'] = confidence
    result['prob_long'] = 0.0
    result['prob_short'] = 0.0
    result['prob_neutral'] = 0.0
    result['volatility'] = df['close'].pct_change().ewm(span=100).std()
    result['atr'] = None
    result['year'] = result.index.year
    result['regime'] = 'unknown'
    return result
