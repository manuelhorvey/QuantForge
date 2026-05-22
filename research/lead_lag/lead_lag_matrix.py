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

if __name__ == "__main__":
    # Test with random data
    s1 = pd.Series(np.random.normal(0, 1, 1000))
    s2 = s1.shift(3).fillna(0) + np.random.normal(0, 0.1, 1000) # s1 leads s2 by 3, or s2 lags s1 by 3
    
    # res = compute_lead_lag(s2, s1) # should show lag 3
    # print(res)
    pass
