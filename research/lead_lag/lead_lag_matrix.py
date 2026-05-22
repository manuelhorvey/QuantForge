import os
import logging
import numpy as np
import pandas as pd
from scipy.signal import correlate
from statsmodels.tsa.stattools import grangercausalitytests

logger = logging.getLogger("quantforge.lead_lag")

def compute_lead_lag(series1: pd.Series, series2: pd.Series, max_lag: int = 21) -> dict:
    """
    Computes lead-lag relationship between two return series.
    Returns max correlation, the lag at which it occurs, and Granger causality p-value.
    """
    # 1. Cross-correlation
    s1 = (series1 - series1.mean()) / (series1.std() * len(series1))
    s2 = (series2 - series2.mean()) / series2.std()
    
    corr = correlate(s1, s2, mode='full')
    lags = np.arange(-len(s1) + 1, len(s1))
    
    # Restrict to max_lag
    mask = (lags >= -max_lag) & (lags <= max_lag)
    subset_corr = corr[mask]
    subset_lags = lags[mask]
    
    idx = np.argmax(np.abs(subset_corr))
    max_corr = subset_corr[idx]
    best_lag = subset_lags[idx]
    
    # 2. Granger Causality
    # We test if series2 leads series1 (lagged series2 helps predict series1)
    # Data must be (n, 2) where col1 is target, col2 is predictor
    data = pd.concat([series1, series2], axis=1).dropna()
    granger_p = 1.0
    try:
        # Check lags 1 to max_lag
        res = grangercausalitytests(data, maxlag=max_lag, verbose=False)
        # Get minimum p-value across all lags
        granger_p = min([res[i][0]['ssr_ftest'][1] for i in range(1, max_lag + 1)])
    except Exception as e:
        logger.debug(f"Granger test failed: {e}")
        
    return {
        "max_corr": float(max_corr),
        "best_lag": int(best_lag),
        "granger_p": float(granger_p)
    }

def build_lead_lag_matrix(series_dict: dict, max_lag: int = 21) -> pd.DataFrame:
    """
    Builds a matrix of lead-lag relationships for all pairs.
    Each cell (A, B) contains best_lag where positive means B leads A.
    """
    names = list(series_dict.keys())
    matrix = pd.DataFrame(index=names, columns=names)
    
    for i, name1 in enumerate(names):
        for j, name2 in enumerate(names):
            if i == j:
                matrix.loc[name1, name2] = 0
                continue
            
            res = compute_lead_lag(series_dict[name1], series_dict[name2], max_lag=max_lag)
            # best_lag > 0 means name2 leads name1
            matrix.loc[name1, name2] = res["best_lag"]
            
    return matrix


def plot_lead_lag_heatmap(matrix: pd.DataFrame, out_path: str, title: str = "Lead-lag (days)") -> str | None:
    """Save a heatmap PNG of the lead-lag matrix. Returns path or None if matplotlib missing."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib not available; skipping lead-lag heatmap")
        return None

    numeric = matrix.astype(float)
    fig, ax = plt.subplots(figsize=(10, 8))
    im = ax.imshow(numeric.values, cmap="RdBu_r", aspect="auto", vmin=-21, vmax=21)
    ax.set_xticks(range(len(numeric.columns)))
    ax.set_yticks(range(len(numeric.index)))
    ax.set_xticklabels(numeric.columns, rotation=90, fontsize=7)
    ax.set_yticklabels(numeric.index, fontsize=7)
    ax.set_title(title)
    fig.colorbar(im, ax=ax, label="best lag (days)")
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    logger.info("Saved lead-lag heatmap to %s", out_path)
    return out_path


if __name__ == "__main__":
    # Test with random data
    s1 = pd.Series(np.random.normal(0, 1, 1000))
    s2 = s1.shift(3).fillna(0) + np.random.normal(0, 0.1, 1000) # s1 leads s2 by 3, or s2 lags s1 by 3
    
    # res = compute_lead_lag(s2, s1) # should show lag 3
    # print(res)
    pass
