import os
import sys
import logging
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from features.registry import FEATURE_REGISTRY
from research.lead_lag.lead_lag_matrix import (
    build_lead_lag_matrix,
    compute_lead_lag,
    plot_lead_lag_heatmap,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("run_lead_lag")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data", "processed")
OUT_DIR = os.path.join(PROJECT_ROOT, "data", "research")

def run():
    os.makedirs(OUT_DIR, exist_ok=True)
    
    # Load daily returns for all assets
    # For now, we'll try to find processed files or load raw
    # Better to use a standard way to get daily returns
    
    series_dict = {}
    tickers = list(FEATURE_REGISTRY.keys())
    
    import yfinance as yf
    for ticker in tickers:
        # Try multiple filename patterns
        clean = ticker.replace('^', '').replace('=', '')
        candidates = [
            f"{clean}_1d.parquet",
            f"{ticker.replace('^', '').replace('=X', '').replace('=F', '')}_1d.parquet",
            f"{ticker}_1d.parquet",
        ]
        found = None
        for c in candidates:
            p = os.path.join(PROJECT_ROOT, "data", "raw", c)
            if os.path.exists(p):
                found = p
                break
        if found is not None:
            df = pd.read_parquet(found)
        else:
            # Fallback to yfinance
            try:
                df = yf.download(ticker, period='10y', auto_adjust=True, progress=False)
                if isinstance(df.columns, pd.MultiIndex):
                    df.columns = [c[0] for c in df.columns]
                df = df.rename(columns={'Close': 'close', 'High': 'high', 'Low': 'low', 'Open': 'open', 'Volume': 'volume'})
                if df.index.tz is None:
                    df.index = df.index.tz_localize('America/New_York')
                else:
                    df.index = df.index.tz_convert('America/New_York')
            except Exception:
                continue
        if "close" in df.columns:
            rets = df["close"].pct_change().dropna()
            if rets.index.tz is None:
                rets.index = rets.index.tz_localize("America/New_York")
            else:
                rets.index = rets.index.tz_convert("America/New_York")
            series_dict[ticker] = rets
            
    if not series_dict:
        logger.error("No data found to compute lead-lag")
        return
        
    logger.info(f"Computing lead-lag for {len(series_dict)} assets...")
    
    results = []
    names = list(series_dict.keys())
    for i, name1 in enumerate(names):
        for j, name2 in enumerate(names):
            if i == j: continue
            
            res = compute_lead_lag(series_dict[name1], series_dict[name2])
            # name2 leads name1 if best_lag > 0
            if res["granger_p"] < 0.05 and abs(res["best_lag"]) > 0:
                results.append({
                    "target": name1,
                    "predictor": name2,
                    "lag": res["best_lag"],
                    "corr": res["max_corr"],
                    "p_val": res["granger_p"]
                })
                
    matrix = build_lead_lag_matrix(series_dict)
    matrix_path = os.path.join(OUT_DIR, "lead_lag_matrix.parquet")
    matrix.to_parquet(matrix_path)
    logger.info("Saved lead-lag matrix to %s", matrix_path)
    plot_lead_lag_heatmap(
        matrix,
        os.path.join(OUT_DIR, "lead_lag_matrix.png"),
        title="Cross-asset lead-lag (best lag, days)",
    )

    df_results = pd.DataFrame(results)
    if not df_results.empty:
        df_results = df_results.sort_values("corr", ascending=False)
        out_path = os.path.join(OUT_DIR, "lead_lag_results.parquet")
        df_results.to_parquet(out_path)
        logger.info(f"Saved {len(df_results)} significant relationships to {out_path}")
        
        print("\nTop 10 Significant Lead-Lag Relationships:")
        print(df_results.head(10))
    else:
        logger.info("No significant relationships found")

if __name__ == "__main__":
    run()
