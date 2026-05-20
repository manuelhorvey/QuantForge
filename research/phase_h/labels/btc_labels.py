"""BTC labels: volatility-adjusted triple barrier (tb-vol).

Standard tb20 uses fixed pt_sl multipliers on close price. For BTC,
endogenous volatility makes fixed multipliers structurally misaligned:
a 3% barrier in low-vol regime is equivalent to 15% in high-vol regime.

tb-vol scales barriers by ATR at entry time, making labels
volatility-regime-adaptive.

Label mapping (to match XGBoost class convention):
  2 = LONG  (upper barrier hit first — price went up)
  0 = SHORT (lower barrier hit first — price went down)
  1 = NEUTRAL (no barrier hit within max_horizon)
"""

import numpy as np
import pandas as pd


def compute_atr(high, low, close, period=14):
    tr = np.maximum(high - low, np.maximum(
        abs(high - close.shift(1)), abs(low - close.shift(1))
    ))
    return tr.rolling(period).mean()


def label_btc_tbvol(
    df: pd.DataFrame,
    pt_mult: float = 2.0,
    sl_mult: float = 1.5,
    max_horizon: int = 20,
    atr_period: int = 14,
) -> pd.Series:
    """Volatility-adjusted triple barrier labels for BTC.

    Barriers are ATR-scaled (absolute price units) instead of
    close-price-vol-scaled. This captures gap risk and intraday range.

    Args:
        df: DataFrame with columns [open, high, low, close]
        pt_mult: take-profit as multiple of ATR at entry
        sl_mult: stop-loss as multiple of ATR at entry
        max_horizon: maximum bars to hold before timeout
        atr_period: ATR computation window

    Returns:
        Series of labels (0=SHORT, 1=NEUTRAL, 2=LONG) with same index as df
    """
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    atr = compute_atr(df['high'], df['low'], df['close'], atr_period).values

    N = len(df)
    labels = np.full(N, 1, dtype=int)  # default NEUTRAL

    for i in range(N - 1):
        atr_i = atr[i]
        if pd.isna(atr_i) or atr_i <= 0:
            continue

        entry = close[i]
        upper_barrier = entry + atr_i * pt_mult
        lower_barrier = entry - atr_i * sl_mult

        end = min(i + 1 + max_horizon, N)
        for j in range(i + 1, end):
            bar_high = high[j]
            bar_low = low[j]

            # Upper hit first → LONG (2)
            if bar_high >= upper_barrier:
                labels[i] = 2
                break
            # Lower hit first → SHORT (0)
            if bar_low <= lower_barrier:
                labels[i] = 0
                break
            # If both on same bar, upper hit has priority (checked first)

    return pd.Series(labels, index=df.index, name='label')
