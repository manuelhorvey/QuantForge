"""
Driver Atlas — Asset-specific feature clusters, exclusion list, and research queue.

Each ticker belongs to a driver cluster that determines which features are relevant.
The cluster taxonomy (ADR-010) is:
  - yield_equity     (XLF, QQQ)       → rate_diff, yield_delta, vs_SPY momentum
  - carry_fx         (NZDJPY, AUDJPY) → VIX, bilateral yield spread, carry momentum
  - momentum_crypto  (BTC-USD, ETH-USD) → momentum features, vol scaling
  - bilateral_fx     (USDCAD, EURUSD) → bilateral rate diff, commodity, cross-asset
  - real_yield       (GC=F)           → real_yield_10y, breakevens, DXY
  - generic_fx       (fallback)       → rate_diff, dxy_mom_21, vix_ma21, pair_mom_21
"""

from __future__ import annotations

from typing import TypedDict


class AssetCluster(TypedDict, total=False):
    cluster: str
    status: str
    scan_result: str
    hypothesis: str
    priority: int
    notes: str


DRIVER_CLUSTERS: dict[str, str] = {
    # Yield-sensitive equities
    "XLF": "yield_equity",
    "QQQ": "yield_equity",
    # Carry FX
    "NZDJPY=X": "carry_fx",
    # Momentum crypto
    "BTC-USD": "momentum_crypto",
    # Real yield / commodities
    "GC=F": "real_yield",
    # Bilateral FX (commodity / rate-differential driven)
    "USDCAD=X": "bilateral_fx",
    "EURUSD=X": "bilateral_fx",
}

EXCLUDED_PERMANENTLY: dict[str, str] = {
    "EURCAD=X": "0/7 positive — no identified driver cluster",
    "CHFJPY=X": "0/7 positive — no identified driver cluster",
    "CADJPY=X": "0/7 positive — negative expectancy all windows",
    "CADCHF=X": "0/7 positive — no identified driver cluster",
    "GBPCHF=X": "0/7 positive — no identified driver cluster",
    "AUDNZD=X": "0/7 positive — no identified driver cluster",
    "GBPCAD=X": "0/7 positive — no identified driver cluster",
}

RESEARCH_QUEUE: dict[str, AssetCluster] = {
    "USDCAD=X": {
        "cluster": "bilateral_fx",
        "status": "candidate",
        "scan_result": "5/7 positive, PF 1.07, generic features",
        "hypothesis": "oil_mom_63 + boc_fed_diff + usdcad_mom_63",
        "priority": 1,
        "notes": "Post-November paper trade review. Needs WTI data + BoC rate series.",
    },
    "AUDJPY=X": {
        "cluster": "carry_fx",
        "status": "candidate",
        "scan_result": "3/7 positive, PF 0.95, generic features — untested with carry_fx config",
        "hypothesis": "Copy NZDJPY=X feature config (vix_ma21, vix_delta_5, us_jp_10y_spread, audjpy_mom_21)",
        "priority": 2,
        "notes": "One walk-forward to test. Already have all data (VIX, US/JP yields).",
    },
    "ETH-USD": {
        "cluster": "momentum_crypto",
        "status": "candidate",
        "scan_result": "Not yet scanned",
        "hypothesis": "Copy BTC-USD feature config (momentum features + vol scaling)",
        "priority": 2,
        "notes": "One walk-forward to test. Already have momentum feature pipeline.",
    },
    "GC=F": {
        "cluster": "real_yield",
        "status": "needs_data",
        "scan_result": "3/7 positive, PF 0.98 — real_yield features partially integrated",
        "hypothesis": "Integration of DFII10 breakevens into walk-forward feature set",
        "priority": 3,
        "notes": "DFII10 already in macro_loader. Needs feature module update + walk-forward rerun.",
    },
    "USDJPY=X": {
        "cluster": "bilateral_fx",
        "status": "needs_rerun",
        "scan_result": "4/7 positive but negative avg expectancy (-0.000025)",
        "hypothesis": "Add BoJ YCC proxy: jp_10y relative to yield curve ceiling",
        "priority": 3,
        "notes": "Negative avg expectancy masks 4/7 win count. Needs bilateral feature isolation test.",
    },
}


def cluster_for(ticker: str) -> str:
    return DRIVER_CLUSTERS.get(ticker, "generic_fx")


def is_eligible(ticker: str) -> bool:
    return ticker not in EXCLUDED_PERMANENTLY
