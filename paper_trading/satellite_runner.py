import logging

import numpy as np
import pandas as pd

from paper_trading.data_fetcher import fetch_live, flatten, safe_download

logger = logging.getLogger("quantforge.satellite_runner")


def fetch_macro_context() -> tuple:
    """Fetch VIX level and DXY momentum for satellite gating."""
    vix = 0.0
    dxy_mom = 0.0
    try:
        vix_df = safe_download("^VIX", period="1mo", auto_adjust=True, progress=False)
        if not vix_df.empty:
            vix_df = flatten(vix_df)
            vix = float(vix_df["close"].ffill().iloc[-1])
    except Exception:
        pass
    try:
        dxy_df = safe_download("DX-Y.NYB", period="3mo", auto_adjust=True, progress=False)
        if not dxy_df.empty:
            dxy_df = flatten(dxy_df)
            dxy_21d_ago = (
                float(dxy_df["close"].ffill().iloc[-22])
                if len(dxy_df) >= 22
                else float(dxy_df["close"].ffill().iloc[0])
            )
            dxy_now = float(dxy_df["close"].ffill().iloc[-1])
            dxy_mom = (dxy_now - dxy_21d_ago) / max(dxy_21d_ago, 1e-10)
    except Exception:
        pass
    return vix, dxy_mom


def compute_btc_context(price_data: pd.DataFrame | None) -> dict:
    """Compute BTC volatility z-score and returns from price data."""
    ctx = {"returns_63d": None, "returns_all": None, "vol_zscore": 0.0}
    if price_data is None or price_data.empty:
        return ctx

    close = price_data["close"].ffill() if "close" in price_data.columns else price_data["close"]
    returns_all = close.pct_change().dropna()
    ctx["returns_all"] = returns_all.values
    ctx["returns_63d"] = returns_all.values[-63:] if len(returns_all) >= 63 else returns_all.values

    vol_21 = float(returns_all[-21:].std()) if len(returns_all) >= 21 else 0.0
    vol_252 = float(returns_all[-252:].std()) if len(returns_all) >= 252 else vol_21
    ctx["vol_zscore"] = (vol_21 - vol_252) / max(vol_252, 1e-10) if vol_252 > 0 else 0.0
    return ctx


def compute_core_returns(assets: dict) -> np.ndarray | None:
    """Compute weighted core portfolio returns over a 63-day window."""
    core_values = [a.pos_mgr.current_value for a in assets.values() if hasattr(a, "pos_mgr") and a.pos_mgr is not None]
    if not core_values:
        return None

    core_total = sum(core_values)
    core_weights = [v / max(core_total, 1) for v in core_values]
    core_returns_list = []
    for a in assets.values():
        if hasattr(a, "signal_data") and a.signal_data is not None and "close" in a.signal_data.columns:
            cr = a.signal_data["close"].pct_change().dropna().values[-63:]
            core_returns_list.append(cr)
    if not core_returns_list:
        return None

    min_len = min(len(cr) for cr in core_returns_list)
    aligned = np.array([cr[-min_len:] for cr in core_returns_list])
    return np.average(aligned, axis=0, weights=core_weights[: len(aligned)])


def fetch_btc_price(assets: dict) -> pd.DataFrame | None:
    """Fetch BTC price data from engine assets or independently."""
    btc_engine = assets.get("BTC")
    if btc_engine is not None and btc_engine.price_data is not None:
        return btc_engine.price_data

    # Independently fetch
    df = fetch_live("BTC-USD", min_days=100)

    # Patch with real-time price
    from paper_trading.data_fetcher import fetch_realtime_price

    lp = fetch_realtime_price("BTC-USD")
    if lp is not None:
        df.loc[df.index[-1], "close"] = lp
    return df
