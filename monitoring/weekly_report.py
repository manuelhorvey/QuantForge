import json
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(BASE, "data", "live", "state.json")
HISTORY_PATH = os.path.join(BASE, "data", "live", "history.parquet")
LOG_PATH = os.path.join(BASE, "data", "live", "weekly_log.csv")
TRADE_LOG_PATH = os.path.join(BASE, "data", "live", "paper_trade_log.md")

# Backtest baselines for signal distribution comparison
BACKTEST_BASELINES = {
    "XLF": {"buy_pct": 35, "sell_pct": 35, "flat_pct": 30, "mean_conf": 0.60},
    "BTC": {"buy_pct": 40, "sell_pct": 30, "flat_pct": 30, "mean_conf": 0.55},
    "NZDJPY": {"buy_pct": 45, "sell_pct": 25, "flat_pct": 30, "mean_conf": 0.55},
}

# Vol regime baselines (training period 2015-2022, EWM span=100)
TRAIN_VOLS = {
    "XLF": 0.0134,
    "BTC": 0.0377,
    "NZDJPY": 0.0070,
}

TICKERS = {
    "XLF": "XLF",
    "BTC": "BTC-USD",
    "NZDJPY": "NZDJPY=X",
}

VOL_RATIO_THRESHOLDS = {
    "healthy": (0.80, 1.20),
    "warning": (0.70, 1.30),
    "critical": (0.50, 1.50),
}


def compute_live_ewm_vol(ticker, span=100):
    df = yf.download(ticker, period="3mo", auto_adjust=True, progress=False)
    if df.empty:
        return None
    close = df["Close"] if "Close" in df.columns else df["close"]
    if isinstance(close, pd.DataFrame):
        close = close.iloc[:, 0]
    log_ret = np.log(close).diff()
    vol = log_ret.ewm(span=span).std()
    vals = vol.dropna()
    return float(vals.iloc[-1]) if not vals.empty else None


def check_vol_regime():
    print("\n--- Vol Regime Check ---")
    all_healthy = True
    for name, ticker in TICKERS.items():
        train_vol = TRAIN_VOLS.get(name)
        live_vol = compute_live_ewm_vol(ticker)
        if live_vol is None or train_vol is None:
            print(f"  {name:8s}: unable to compute vol")
            continue
        ratio = live_vol / train_vol

        if ratio < VOL_RATIO_THRESHOLDS["critical"][0] or ratio > VOL_RATIO_THRESHOLDS["critical"][1]:
            status = "CRITICAL"
            all_healthy = False
        elif ratio < VOL_RATIO_THRESHOLDS["warning"][0] or ratio > VOL_RATIO_THRESHOLDS["warning"][1]:
            status = "WARNING"
            all_healthy = False
        elif ratio < VOL_RATIO_THRESHOLDS["healthy"][0] or ratio > VOL_RATIO_THRESHOLDS["healthy"][1]:
            status = "WARNING"
        else:
            status = "healthy"

        print(
            f"  {name:8s}: train_vol={train_vol:.4f}  live_vol={live_vol:.4f}  "
            f"ratio={ratio:.2f}  → {status}"
            f"{' ⚠' if status != 'healthy' else ''}"
        )
    return all_healthy


def log_vol_baseline():
    entries = []
    for name, ticker in TICKERS.items():
        train_vol = TRAIN_VOLS.get(name)
        live_vol = compute_live_ewm_vol(ticker)
        if live_vol is None:
            continue
        ratio = live_vol / train_vol
        entries.append((name, train_vol, live_vol, ratio))
    today = datetime.now().strftime("%Y-%m-%d")

    md = (
        f"# Paper Trade Log\n\n"
        f"## {today} — Vol Regime Baseline\n\n"
        f"Initial vol regime readings at paper trade start. "
        f"Training period: 2015-2022, EWM span=100.\n\n"
        f"| Asset | Train Vol | Live Vol | Ratio | Status |\n"
        f"|-------|-----------|----------|-------|--------|\n"
    )
    for name, tv, lv, ratio in entries:
        if ratio < VOL_RATIO_THRESHOLDS["critical"][0] or ratio > VOL_RATIO_THRESHOLDS["critical"][1]:
            status = "CRITICAL"
        elif ratio < VOL_RATIO_THRESHOLDS["warning"][0] or ratio > VOL_RATIO_THRESHOLDS["warning"][1]:
            status = "WARNING"
        else:
            status = "healthy"
        md += f"| {name:6s} | {tv:.4f} | {lv:.4f} | {ratio:.2f} | {status} |\n"

    md += (
        "\nLive vol is structurally lower than 2015-2022 training period. "
        "Walk-forward already captured some of this — 2022-2024 windows\n"
        "showed lower vol than early training years. Effect on performance "
        "to be measured over 6-month paper trade period.\n"
        "Action: retrain with vol-adjusted barriers in January 2027.\n"
    )

    # Append to log
    if os.path.exists(TRADE_LOG_PATH):
        with open(TRADE_LOG_PATH) as f:
            existing = f.read()
        if today not in existing:
            with open(TRADE_LOG_PATH, "a") as f:
                f.write("\n\n" + md)
    else:
        os.makedirs(os.path.dirname(TRADE_LOG_PATH), exist_ok=True)
        with open(TRADE_LOG_PATH, "w") as f:
            f.write(md)
    print(f"\nVol baseline logged to {TRADE_LOG_PATH}")


def run():
    state = load_state()
    if state is None:
        print("No state found.")
        return
    hist = load_history()

    print("\n" + "=" * 70)
    print(f"WEEKLY PORTFOLIO REPORT — {datetime.now().strftime('%Y-%m-%d')}")
    print("=" * 70)

    portfolio = state.get("portfolio", {})
    tv = portfolio.get("total_value", 0)
    tr = portfolio.get("total_return", 0)
    days = portfolio.get("days_running", 0)
    print(f"\nPortfolio: ${tv:,.2f}  Return: {tr:+.2f}%  Days: {days}")

    # Signal distribution check
    print("\n--- Signal Distribution Check ---")
    for name in ["XLF", "BTC", "NZDJPY"]:
        asset = state.get("assets", {}).get(name, {})
        metrics = asset.get("metrics", {})
        sig_dist = metrics.get("signal_distribution", {})
        buy = sig_dist.get("BUY", 0)
        sell = sig_dist.get("SELL", 0)
        flat = sig_dist.get("FLAT", 0)
        total = buy + sell + flat
        buy_pct = buy / total * 100 if total > 0 else 0
        sell_pct = sell / total * 100 if total > 0 else 0
        baseline = BACKTEST_BASELINES.get(name, {})
        b_buy = baseline.get("buy_pct", 33)
        b_sell = baseline.get("sell_pct", 33)

        buy_drift = abs(buy_pct - b_buy)
        sell_drift = abs(sell_pct - b_sell)
        stable = buy_drift < 15 and sell_drift < 15

        print(
            f"  {name:8s}: Live B/S {buy_pct:.0f}/{sell_pct:.0f} vs BT {b_buy}/{b_sell} "
            f"→ {'STABLE' if stable else 'DRIFT'} "
            f"(buy_d={buy_drift:.0f}pp sell_d={sell_drift:.0f}pp)"
        )

    # Confidence drift check
    print("\n--- Confidence Trend Check ---")
    for name in ["XLF", "BTC", "NZDJPY"]:
        asset = state.get("assets", {}).get(name, {})
        metrics = asset.get("metrics", {})
        mean_conf = metrics.get("mean_confidence", 0) / 100
        baseline_conf = BACKTEST_BASELINES.get(name, {}).get("mean_conf", 0.55)
        drift = abs(mean_conf - baseline_conf)
        print(
            f"  {name:8s}: Live conf={mean_conf:.2f} vs BT={baseline_conf:.2f} "
            f"→ {'STABLE' if drift < 0.15 else 'DRIFT'} (d={drift:.3f})"
        )

    # Drawdown warning
    print("\n--- Drawdown Status ---")
    for name in ["XLF", "BTC", "NZDJPY"]:
        asset = state.get("assets", {}).get(name, {})
        metrics = asset.get("metrics", {})
        dd = metrics.get("drawdown", 0) / 100
        limits = {"XLF": -0.08, "BTC": -0.15, "NZDJPY": -0.06}
        limit = limits.get(name, -0.10)
        pct_to_halt = (dd - limit) / abs(limit) * 100 if limit < 0 else 0
        print(f"  {name:8s}: DD={dd:.2%} limit={limit:.0%} → {pct_to_halt:.0f}% of halt distance")

    # Vol regime check
    check_vol_regime()
    log_vol_baseline()

    # Weekly PnL
    if len(hist) > 5:
        print("\n--- Weekly PnL ---")
        recent = hist.tail(7)
        for _, r in recent.iterrows():
            date = r.get("date", "")
            pnl_pct = 0
            for name in ["XLF", "BTC", "NZDJPY"]:
                pnl_pct += r.get(f"{name}_return", 0) / 3
            print(f"  {date}: avg return {pnl_pct:+.2f}%")

    # Log to CSV
    log_entry = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "portfolio_value": tv,
        "portfolio_return": tr,
        "days_running": days,
    }
    for name in ["XLF", "BTC", "NZDJPY"]:
        asset = state.get("assets", {}).get(name, {})
        metrics = asset.get("metrics", {})
        log_entry[f"{name}_return"] = metrics.get("total_return", 0)
        log_entry[f"{name}_dd"] = metrics.get("drawdown", 0)
        log_entry[f"{name}_pf"] = metrics.get("profit_factor", 0)
        sig_dist = metrics.get("signal_distribution", {})
        log_entry[f"{name}_buy_pct"] = sig_dist.get("BUY", 0)
        log_entry[f"{name}_sell_pct"] = sig_dist.get("SELL", 0)
        live_vol = compute_live_ewm_vol(TICKERS[name])
        if live_vol is not None:
            log_entry[f"{name}_vol_ratio"] = round(live_vol / TRAIN_VOLS[name], 2)
    log_df = pd.DataFrame([log_entry])
    if os.path.exists(LOG_PATH):
        existing = pd.read_csv(LOG_PATH)
        log_df = pd.concat([existing, log_df], ignore_index=True)
    log_df.to_csv(LOG_PATH, index=False)
    print(f"\nWeekly log saved to {LOG_PATH}")


def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return None


def load_history():
    if os.path.exists(HISTORY_PATH):
        return pd.read_parquet(HISTORY_PATH)
    return pd.DataFrame()


if __name__ == "__main__":
    run()
