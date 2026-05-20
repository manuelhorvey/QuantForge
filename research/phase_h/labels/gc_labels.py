"""GC labels: long-horizon forward return classification.

GC is a macro-driven drift system where edge is time-dilated.
Standard fwd60 (60-bar forward return) is too short — GC's trend
structure operates at 120-260 bar horizons.

Label scheme:
  2 = LONG  (forward return > +threshold)
  0 = SHORT (forward return < -threshold)
  1 = NEUTRAL (forward return within threshold)
"""

import numpy as np
import pandas as pd


def label_gc_forward_return(
    df: pd.DataFrame,
    horizon: int = 120,
    threshold: float = 0.03,
) -> pd.Series:
    """Long-horizon forward return labels for GC.

    Args:
        df: DataFrame with 'close' column
        horizon: number of bars to look forward
        threshold: minimum absolute return to classify as directional (e.g. 0.03 = 3%)

    Returns:
        Series of labels (0=SHORT, 1=NEUTRAL, 2=LONG) with same index as df
    """
    close = df['close'].values
    N = len(df)
    labels = np.full(N, 1, dtype=int)  # default NEUTRAL

    for i in range(N - horizon):
        ret = close[i + horizon] / close[i] - 1.0

        if ret > threshold:
            labels[i] = 2  # LONG — price went up
        elif ret < -threshold:
            labels[i] = 0  # SHORT — price went down
        # else: NEUTRAL

    return pd.Series(labels, index=df.index, name='label')
