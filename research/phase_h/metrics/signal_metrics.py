"""Signal metrics — entry quality assessment for Phase H.

Measures:
  - directional accuracy (does the signal predict correct direction?)
  - entry timing Sharpe (fixed-exit PnL from signals)
  - flip consistency (how often signals reverse rapidly)
"""

import numpy as np
import pandas as pd


def compute_signal_metrics(
    predictions: pd.DataFrame,
    forward_horizon: int = 1,
) -> dict:
    """Compute signal quality metrics for a prediction set.

    Args:
        predictions: DataFrame with [close, signal] columns
        forward_horizon: bars to look ahead for correctness check

    Returns:
        dict with signal quality metrics
    """
    close = predictions['close'].values
    signal = predictions['signal'].values.astype(int)
    N = len(predictions)

    # Directional accuracy: was signal correct N bars later?
    future_close = np.full(N, np.nan)
    future_close[:N - forward_horizon] = close[forward_horizon:]
    price_change = future_close / close - 1.0

    long_signals = signal == 2
    short_signals = signal == 0
    directional = long_signals | short_signals

    long_correct = long_signals & (price_change > 0) if forward_horizon <= N else np.zeros(N, dtype=bool)
    short_correct = short_signals & (price_change < 0) if forward_horizon <= N else np.zeros(N, dtype=bool)
    correct = long_correct | short_correct

    n_directional = directional.sum()
    n_correct = correct.sum()
    directional_accuracy = n_correct / n_directional if n_directional > 0 else 0.0

    # Flip consistency: signal that reverses within k bars
    flip_window = 3
    flips = np.zeros(N, dtype=bool)
    for i in range(N - flip_window):
        if directional[i]:
            future = signal[i + 1:i + 1 + flip_window]
            if signal[i] == 2:
                flips[i] = np.any(future == 0)
            else:
                flips[i] = np.any(future == 2)
    flip_rate = flips.sum() / n_directional if n_directional > 0 else 0.0

    # Signal distribution
    n_long = int(long_signals.sum())
    n_short = int(short_signals.sum())
    n_neutral = int((signal == 1).sum())

    # Entry timing Sharpe (quick fixed-exit PnL)
    test_rets = np.zeros(N)
    test_rets[long_signals] = price_change[long_signals] if forward_horizon <= N else 0
    test_rets[short_signals] = -price_change[short_signals] if forward_horizon <= N else 0
    trades_only = test_rets[directional]
    if len(trades_only) > 10 and trades_only.std() > 0:
        timing_sharpe = trades_only.mean() / trades_only.std() * np.sqrt(252)
    else:
        timing_sharpe = 0.0

    # Confidence stats
    confidence = predictions['confidence'].values
    conf_mean = float(confidence.mean()) if len(confidence) > 0 else 0.0

    return {
        'n_total': N,
        'n_directional': int(n_directional),
        'n_long': n_long,
        'n_short': n_short,
        'n_neutral': n_neutral,
        'long_pct': round(n_long / n_directional * 100, 1) if n_directional > 0 else 0.0,
        'directional_accuracy': round(float(directional_accuracy), 4),
        'flip_rate': round(float(flip_rate), 4),
        'timing_sharpe': round(float(timing_sharpe), 4),
        'mean_confidence': round(float(conf_mean), 2),
    }
