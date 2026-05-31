from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pandas as pd

VOLATILITY_PRIMITIVE_VERSION = "1.0.0"


class ATRMode(str, Enum):
    CLOSE = "close"
    HIGH_LOW = "high_low"
    EXPONENTIAL = "exponential"


@dataclass
class VolatilityPrimitive:
    window: int = 14
    mode: ATRMode = ATRMode.CLOSE
    min_periods: int = 5
    version: str = VOLATILITY_PRIMITIVE_VERSION


def compute_atr_series(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr = pd.concat(
        [
            (high - low).abs(),
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(window=window, min_periods=window).mean()


def compute_atr_pct(df: pd.DataFrame, window: int = 14) -> pd.Series:
    atr = compute_atr_series(df, window=window)
    close = df["close"]
    return atr / close.where(close != 0, 1)


def compute_latest_atr(df: pd.DataFrame, window: int = 14) -> float:
    atr = compute_atr_series(df, window=window)
    return float(atr.iloc[-1]) if not atr.empty else 0.0


def compute_latest_atr_pct(df: pd.DataFrame, window: int = 14) -> float:
    atr_pct = compute_atr_pct(df, window=window)
    return float(atr_pct.iloc[-1]) if not atr_pct.empty else 0.0


def estimate_gap_risk(df: pd.DataFrame, window: int = 20) -> float:
    if len(df) < 2:
        return 0.0
    gaps = (df["open"] - df["close"].shift()).abs() / df["close"].shift().where(df["close"].shift() != 0, 1)
    return float(gaps.rolling(window=window).mean().iloc[-1]) if not gaps.empty else 0.0


def estimate_ewm_vol(returns: pd.Series, span: int = 21) -> float:
    if returns.empty:
        return 0.0
    return float(returns.ewm(span=span).std().iloc[-1])
