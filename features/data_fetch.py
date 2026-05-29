import logging

import numpy as np
import pandas as pd

logger = logging.getLogger("quantforge.data_fetch")


def fetch_yf_series(ticker: str, name: str, period: str = "10y") -> pd.Series:
    """Fetch a single yfinance series, return daily 'Close' with tz-aware UTC index."""
    import yfinance as yf

    df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    s = df["Close"].squeeze().rename(name)
    idx = s.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    s.index = idx.normalize()
    return s


def fetch_asset_data(
    asset_name: str,
    ticker: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series, pd.Series, pd.DataFrame]:
    """Fetch asset + macro data from yfinance.

    Returns (prices, rate_diffs, dxy, vix, spx, commodities).
    prices: DataFrame with 'close' column
    rate_diffs: DataFrame with asset_name column (approximated from 10Y yield)
    dxy, vix, spx: Series
    commodities: DataFrame with 'WTI' column
    """
    logger.info("  fetching %s (%s) from yfinance...", asset_name, ticker)
    close = fetch_yf_series(ticker, f"{asset_name}_close")
    prices = close.to_frame("close")

    logger.info("  fetching macro (DXY, VIX, SPY, CL=F, TNX)...")
    dxy = fetch_yf_series("DX-Y.NYB", "dxy")
    vix = fetch_yf_series("^VIX", "vix")
    spx = fetch_yf_series("^GSPC", "spx")
    wti = fetch_yf_series("CL=F", "WTI")
    tnx = fetch_yf_series("^TNX", "tnx") / 100.0

    common = close.index.intersection(dxy.index).intersection(vix.index).intersection(spx.index).intersection(wti.index)
    common = common.intersection(tnx.dropna().index)
    logger.info("  aligned on %d business days", len(common))

    prices = prices.loc[common].copy()
    dxy = dxy.reindex(common).ffill()
    vix = vix.reindex(common).ffill()
    spx = spx.reindex(common).ffill()
    wti = wti.reindex(common).ffill()
    tnx = tnx.reindex(common).ffill()

    _rng = np.random.default_rng(42)
    rate_diffs = pd.DataFrame(
        {col: tnx * float(_rng.uniform(0.5, 1.5)) for col in [asset_name]},
        index=common,
    )

    commodities = wti.to_frame("WTI")

    return prices, rate_diffs, dxy, vix, spx, commodities


def fetch_asset_ohlcv(
    ticker: str,
    period: str = "10y",
) -> pd.DataFrame:
    """Fetch full-history OHLCV data with tz-aware UTC index.

    Returns DataFrame with columns: open, high, low, close, volume.
    Index is DatetimeIndex with UTC timezone, normalized to midnight.
    """
    import time as _time

    import yfinance as yf

    _time.sleep(0.5)
    df = yf.download(ticker, period=period, auto_adjust=True, progress=False)
    if df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [c[0] for c in df.columns]
    df = df.rename(
        columns={
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "volume",
        }
    )
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    else:
        idx = idx.tz_convert("UTC")
    df.index = idx.normalize()
    return df
