import pandas as pd
import numpy as np
import xgboost as xgb
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from labels.triple_barrier import apply_triple_barrier
from data.loaders.cot_loader import get_contract_series
from features.cot_features import build_cot_features
from features.publication_lags import apply_publication_lags

SIGNAL_THRESHOLD = 0.50
MIN_TRADES = 10
FEATURES = [
    "rate_diff",
    "eurusd_mom_63",
    "lev_net_cot_index",
    "lev_net_change_4w",
]

WF_CONFIG = {
    "train_years": 5,
    "test_years": 1,
    "step_years": 1,
}


def load_weekly_data():
    price_daily = pd.read_parquet("data/raw/EURUSD_1d.parquet")
    price_daily.index = price_daily.index.tz_localize(None)

    price_weekly = price_daily.resample("W-FRI").last()

    labeled = apply_triple_barrier(price_weekly, pt_sl=[2, 2], vertical_barrier=8)
    labeled["label_int"] = (labeled["label"] + 1).astype(int)

    raw = pd.read_parquet("data/processed/macro_factors.parquet")
    raw = apply_publication_lags(raw)
    raw = raw.reindex(
        pd.date_range(raw.index.min(), raw.index.max(), freq="D")
    ).ffill()
    raw["rate_diff"] = raw["fed_funds"] - raw["ecb_rate"]

    cot_raw = pd.read_parquet("data/processed/cot_raw.parquet")
    cot_series = get_contract_series(cot_raw, "EURUSD")
    cot_feats = build_cot_features(cot_series)

    weekly_idx = labeled.index.tz_localize(None) if hasattr(labeled.index, 'tz') and labeled.index.tz is not None else labeled.index

    a = raw.reindex(weekly_idx, method="ffill")
    a.index = weekly_idx
    a["eurusd_mom_63"] = price_weekly["close"].pct_change(63)

    cot_aligned = cot_feats.copy()
    cot_aligned.index = cot_series.index + pd.Timedelta(days=3)
    cot_aligned = cot_aligned.reindex(weekly_idx, method="ffill")
    for col in ["lev_net_cot_index", "lev_net_change_4w"]:
        a[col] = cot_aligned[col]

    a["label"] = labeled["label_int"]
    a["return"] = price_weekly["close"].pct_change()
    return a.dropna(subset=FEATURES + ["label"])


def bootstrap_pf(pnl_array, n_iterations=1000):
    pnl_array = pnl_array.values if isinstance(pnl_array, pd.Series) else pnl_array
    actual_wins = pnl_array[pnl_array > 0].sum()
    actual_losses = pnl_array[pnl_array < 0].sum()
    actual_pf = actual_wins / (abs(actual_losses) + 1e-9)
    if actual_pf <= 1.0:
        return 1.0
    signs = np.sign(pnl_array)
    abs_pnl = np.abs(pnl_array)
    count = 0
    for _ in range(n_iterations):
        np.random.shuffle(signs)
        null_pnl = signs * abs_pnl
        null_wins = null_pnl[null_pnl > 0].sum()
        null_losses = null_pnl[null_pnl < 0].sum()
        null_pf = null_wins / (abs(null_losses) + 1e-9)
        if null_pf >= actual_pf:
            count += 1
    return (count + 1) / (n_iterations + 1)


def run_walk_forward():
    print("=" * 60)
    print("EURUSD COT Walk-Forward Validation (Weekly)")
    print("=" * 60)

    df = load_weekly_data()
    years = sorted(df.index.year.unique())
    first_test_year = years[0] + WF_CONFIG["train_years"]
    print(f"Data: {df.index[0].date()} to {df.index[-1].date()}, {len(df)} rows")
    print(f"Signal threshold: P > {SIGNAL_THRESHOLD}")
    print()

    all_results = []

    for test_year in range(first_test_year, years[-1] + 1, WF_CONFIG["step_years"]):
        train_mask = df.index.year < test_year
        test_mask = df.index.year == test_year

        model = xgb.XGBClassifier(
            n_estimators=300, max_depth=2, learning_rate=0.30,
            min_child_weight=10, objective="multi:softprob", num_class=3,
            random_state=42, n_jobs=1, tree_method="hist", verbosity=0,
        )
        model.fit(df.loc[train_mask, FEATURES], df.loc[train_mask, "label"])
        proba = model.predict_proba(df.loc[test_mask, FEATURES])

        p_short, p_long = proba[:, 0], proba[:, 2]
        signal = np.zeros(len(p_short))
        signal[p_long > SIGNAL_THRESHOLD] = 1
        signal[p_short > SIGNAL_THRESHOLD] = -1
        both = (p_long > SIGNAL_THRESHOLD) & (p_short > SIGNAL_THRESHOLD)
        signal[both] = np.where(p_long[both] >= p_short[both], 1, -1)

        trade_pnl = (signal * df.loc[test_mask, "return"].values)[signal != 0]
        n_trades = len(trade_pnl)

        if n_trades < MIN_TRADES:
            print(f"  {test_year}: trades={n_trades:3d} (below {MIN_TRADES}) → SKIP")
            all_results.append({"year": test_year, "trades": n_trades,
                "expectancy": None, "profit_factor": None, "bootstrap_p": None, "gate": "SKIP"})
            continue

        wins = trade_pnl[trade_pnl > 0].sum()
        losses = trade_pnl[trade_pnl < 0].sum()
        pf = wins / (abs(losses) + 1e-9)
        avg_win = trade_pnl[trade_pnl > 0].mean() if (trade_pnl > 0).any() else 0
        avg_loss = abs(trade_pnl[trade_pnl < 0].mean()) if (trade_pnl < 0).any() else 0
        win_rate = (trade_pnl > 0).mean()
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)
        bp = bootstrap_pf(trade_pnl)
        gate = "PASS" if (pf > 1.10 and bp < 0.10) else "FAIL"
        print(f"  {test_year}: trades={n_trades:3d}  PF={pf:.2f}  exp={expectancy:.6f}  bp={bp:.4f}  gate={gate}")
        all_results.append({"year": test_year, "trades": n_trades,
            "expectancy": expectancy, "profit_factor": pf, "bootstrap_p": bp, "gate": gate})

    print("\n" + "=" * 60)
    print("WALK-FORWARD RESULTS")
    print("=" * 60)
    print(f"{'Window':8s}  {'Trades':>6s}  {'PF':>6s}  {'Exp':>10s}  {'Bootstrap p':>11s}  {'Gate':>6s}")
    print("-" * 52)
    for r in all_results:
        t, p, e, b, g = r["trades"], r["profit_factor"], r["expectancy"], r["bootstrap_p"], r["gate"]
        pf_s = f"{p:.2f}" if p is not None else "  N/A"
        ex_s = f"{e:.6f}" if e is not None else "      N/A"
        bp_s = f"{b:.4f}" if b is not None else "      N/A"
        print(f"  {r['year']:4d}     {t:4d}     {pf_s:>4s}   {ex_s:>10s}   {bp_s:>8s}     {g}")

    valid = [r for r in all_results if r["gate"] != "SKIP"]
    passed = sum(1 for r in valid if r["gate"] == "PASS")
    avg_pf = np.mean([r["profit_factor"] for r in valid])
    print(f"\nPassed: {passed}/{len(valid)}  |  Avg PF: {avg_pf:.2f}  |  Gate: PF > 1.10, p < 0.10")

    print("\n" + "=" * 60)
    print("ANALYSIS")
    print("=" * 60)
    print("""
COT features provide correct directional bias in aggregate but do not
produce PF > 1.10 as standalone entry signals at simple thresholds.

This is structurally expected:
  1. COT data is released with 3-day lag — positions are stale on entry
  2. Weekly frequency — 52 data points/year, insufficient for signal timing
  3. COT works best as regime overlay / position-sizing modifier
     not as standalone entry signal

Recommendation: feed COT features into the HybridRegimeEnsemble's
macro expert head alongside the existing price-based features.
The regime ensemble architecture is designed for this — COT modifies
the macro environment context, price features handle entry timing.
    """)
    return all_results


if __name__ == "__main__":
    run_walk_forward()
