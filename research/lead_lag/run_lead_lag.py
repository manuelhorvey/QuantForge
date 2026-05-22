import os
import logging
import pandas as pd
from features.registry import FEATURE_REGISTRY
from research.lead_lag.lead_lag_matrix import build_lead_lag_matrix, compute_lead_lag

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
    
    for ticker in tickers:
        # Try to find data
        path = os.path.join(PROJECT_ROOT, "data", "raw", f"{ticker.replace('^', '').replace('=', '')}_1d.parquet")
        if not os.path.exists(path):
            continue
            
        df = pd.read_parquet(path)
        if "close" in df.columns:
            rets = df["close"].pct_change().dropna()
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
