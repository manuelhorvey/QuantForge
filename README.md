# QuantForge

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Status](https://img.shields.io/badge/status-paper%20trading-green)
![WalkForward](https://img.shields.io/badge/walk--forward-30%20assets%20screened-success)
![Portfolio](https://img.shields.io/badge/portfolio-13%20assets%20%7C%20BTC%20satellite-blue)
[![codecov](https://codecov.io/gh/manuelhorvey/QuantForge/graph/badge.svg)](https://codecov.io/gh/manuelhorvey/QuantForge)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

Cross-sectional FX/commodity/crypto factor ranking system with walk-forward validated asset screening, binary XGBoost per-asset models, and a live paper trading execution layer.

## System Overview

QuantForge operates as a **factor-style allocation system**: 30+ tickers are screened via expanding-window walk-forward backtests, scored on IC/hit rate/consistency, and promoted to a live paper portfolio. Each promoted asset runs an independent binary XGBoost model conditioned on alpha features (vol-adjusted carry, multi-horizon momentum, z-score reversion, vol regime, cross-asset macro momentum) with archetype-aware execution and 7-layer governance.

```
┌─────────────┐    ┌──────────────┐    ┌────────────┐    ┌─────────────────┐
│ Screening   │───▶│ Promotion    │───▶│ Live       │───▶│ Portfolio       │
│ 30 tickers  │    │ GREEN/YELLOW │    │ Inference  │    │ 15 assets       │
│ walk-fwd    │    │ RED          │    │ binary XGB │    │ equal-risk wts  │
└─────────────┘    └──────────────┘    └────────────┘    └─────────────────┘
```

| Layer | Description |
|---|---|---|
| **Screening** | 30 tickers via walk-forward (3y window, 1y step, 5 folds, per-asset pt_sl) 15 promoted |
| **Scoring** | Composite score: IC + hit rate + consistency + bidirectionality |
| **Feature Engineering** | Alpha features: vol-adjusted carry, multi-horizon momentum, z-score reversion, vol regime, DOW + cross-asset (DXY/VIX/SPX/WTI mom). Macro tickers batched into single `yf.download` with TTL cache (300s). |
| **Models** | Binary XGBoost (binary:logistic, 300 trees, depth=2, lr=0.02) per asset |
| **Archetype Classification** | 5 pure-feature market structure archetypes from OHLCV (EMA spread, ADX, RSI, BB z-score) |
| **Inference** | Vectorized triple-barrier (`sliding_window_view` + broadcast + argmax). Async diagnostics via daemon consumer thread. Inference truncation with behavioral validation (500d → 250d for hot path). Model hot-swap re-validation on object identity change. |
| **Execution** | EntryOptimizer → ExecutionPolicy → PositionManager with 7-layer governance. All 15 assets run in parallel via `ThreadPoolExecutor(max_workers=8)`. |
| **State** | SQLite-backed state store (WAL mode, 5 tables, O(1) append) with periodic WAL checkpoint. Legacy JSON snapshots preserved for backward compatibility. |
| **Monitoring** | PSI drift, feature stability, narrative governance, liquidity regime, validity state machine |

## Current Portfolio

**15 live assets** promoted from 30-ticker screening (risk-parity allocation):

| Asset | Ticker | Allocation | sl_mult | tp_mult | Walk-forward score | Walk-forward IC |
|---|---|---|---|---|---|---|
| BTCUSD | BTC-USD | 6.5% | 3.0 | 2.5 | 80.9 / 100 | 0.2264 |
| EURGBP | EURGBP=X | 6.5% | 2.0 | 1.5 | 69.0 / 100 | 0.1104 |
| GC | GC=F | 6.5% | 2.0 | 1.5 | 66.7 / 100 | 0.1270 |
| NZDCHF | NZDCHF=X | 6.5% | 2.0 | 1.5 | 70.0 / 100 | 0.1080 |
| CHFJPY | CHFJPY=X | 6.5% | 2.0 | 1.5 | YELLOW | — |
| CADJPY | CADJPY=X | 6.5% | 2.0 | 1.5 | YELLOW | — |
| USDCHF | USDCHF=X | 6.5% | 2.0 | 1.5 | YELLOW | — |
| EURJPY | EURJPY=X | 6.5% | 2.0 | 1.5 | YELLOW | — |
| EURCAD | EURCAD=X | 6.5% | 2.0 | 1.5 | YELLOW | — |
| AUDCHF | AUDCHF=X | 6.5% | 2.0 | 1.5 | YELLOW | — |
| USDJPY | USDJPY=X | 6.5% | 2.0 | 1.5 | YELLOW | — |
| USDCAD | USDCAD=X | 6.5% | 2.0 | 1.5 | YELLOW | — |
| GBPCHF | GBPCHF=X | 6.5% | 2.0 | 1.5 | YELLOW | — |
| ES | ES=F | 7.7% | 2.0 | 2.5 | 76.9 / 100 | 0.1273 |
| NQ | NQ=F | 7.8% | 2.0 | 2.5 | 67.9 / 100 | 0.0932 |

**BTC satellite:** 5% AUM cap, vol target 40%, macro-gated entry (VIX, DXY, vol z-score, portfolio returns, crisis regime), managed by `HighVolSatellite`.

## Architecture

### Data Ingestion

```
yfinance ──▶ fetch_asset_data(name, ticker) ──▶ prices, dxy, vix, spx, wti, tnx
           └── fetch_asset_ohlcv(ticker)     ──▶ full OHLCV for archetype features
```

All data normalized to TZ-naive date index. No FRED data — macro derived from yfinance tickers (DX-Y.NYB, ^VIX, ^GSPC, CL=F, ^TNX).

### Feature Engineering

**Alpha features** (`features/alpha_features.py:build_alpha_features()`):
- Vol-adjusted carry (close returns × vol normalization)
- Multi-horizon momentum (21/63/126/252 day windows)
- Z-score reversion (20-day rolling z-score of close)
- Vol regime ratio (short-term / long-term vol)
- Day-of-week signal
- Cross-asset momentum (DXY, VIX, SPX, WTI over 21/63d)

**Archetype features** (inference-only, from full-history OHLCV):
- EMA spread (EMA20 − EMA50) / EMA50
- ADX(14), RSI(14), BB z-score(20)

### Model Pipeline

```
1. fetch_live(ticker)           → 500d OHLCV, TZ-normalized
2. refresh_price()               → patch last close (realtime or 5d fallback)
3. fetch_asset_data()            → 10y close + macro (batched yf.download, TTL 300s)
4. build_alpha_features()        → alpha_df (~30 feature cols)
5. fetch_asset_ohlcv()           → 10y OHLCV for archetype (no rate-limit sleep)
6. Inference truncation          → 500d → 250d with behavioral validation
7. Model hot-swap validation     → re-validate full chain on object identity change
8. XGBoost predict               → binary → 3-col proba expansion
9. Archetype classification      → 5 types from OHLCV
10. FixedThresholdStrategy(0.45) → BUY/SELL/FLAT
11. Async diagnostics enqueue    → model/feature snapshots off hot path
12. EntryOptimizer → Policy → Position management (via parallel orchestrator)
```

### Training

```
1. fetch_asset_data()            → 10y data
2. triple_barrier_labels(pt_sl)  → {-1, 0, 1}
3. Binary reduction               → drop HOLD, map {-1,1} → {0,1}
4. XGBoost binary:logistic       → 300 trees, depth=2
5. Save .json model              → paper_trading/models/{name}_model.json
6. PSI baseline persist
7. Optional regime model + meta-label model
```

### Execution Pipeline

```
TradeDecision (15 assets in parallel via EngineOrchestrator) 
    → EntryOptimizer → ExecutionPolicyLayer → _can_enter() gate
    → _open_position() → PositionManager (SL/TP/scale-out) → Attribution
    → HealthMonitor tracks per-asset HEALTHY/DEGRADED/HALTED
```

Seven-layer governance: validity state machine, feature stability, meta-labeling, macro narrative (weekly LLM), liquidity regime, PSI drift, portfolio drawdown.

## Getting Started

```bash
git clone https://github.com/user/quantforge.git && cd quantforge
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# Start engine + dashboard:
./monitor_all
# Dashboard: http://localhost:5000
```

### Environment

| Var | Required | Purpose |
|---|---|---|
| `OPENCODE_ZEN_API_KEY` | No | Weekly LLM narrative extraction (Claude API) |
| `PYTHONPATH` | Yes | `PYTHONPATH=.` |
| `QUANTFORGE_REFRESH_INTERVAL` | No | Engine loop interval (default 300s) |

## Key Scripts

| Script | Purpose |
|---|---|
| `scripts/walk_forward_backtest.py --tickers` | Run walk-forward backtest on raw yfinance tickers |
| `scripts/score_tickers.py` | Score tickers and produce promotion report |
| `scripts/generate_promotion_report.py` | Generate markdown report + YAML config block |
| `scripts/train_all_assets.py` | Force-retrain all assets |
| `benchmarks/microbenchmark.py` | Hot-path microbenchmark (cold/warm cycles, sweep, profile) |

## Governance Layers

| Layer | Frequency | Scope | Effect | Doc |
|---|---|---|---|---|
| Validity state machine | Per tick | Per asset | Exposure 0–100% | — |
| Feature stability | Per retrain | Per asset | Validity penalty | — |
| Meta-labeling (XGBoost) | Per signal | Per asset | Size scalar [0–1] | `labels/meta_labels.py` |
| Macro narrative | Weekly | Global | SL +10%, size −20% | `features/macro_narrative.py` |
| Liquidity regime | Per signal | Per asset | SL +15/30%, size −15/30%, halt | `features/liquidity_regime.py` |
| PSI drift | Per cycle | Per asset | Validity penalty, halt at 3+ SEVERE | `monitoring/psi_monitor.py` |

## System Invariants

- No train/serve skew — same alpha feature builder in training and inference
- TZ-naive date alignment across all pipeline stages
- Per-asset model independence — each asset has its own binary XGBoost
- Walk-forward validated — every promoted asset passes 3yr expanding window backtest
- Binary signal — HOLD dropped; model trains on {-1, 1} labels only
- Single entry authority — all entry sources route through `_can_enter()`
- Frozen execution contract — PolicyDecision → FillResult → AttributionRecord immutable chain
- Seven-layer governance — independently configurable, worst-wins aggregation
- Per-asset pt_sl — `tp_mult`/`sl_mult` from config, applied at label time and runtime
- Inference truncation symmetry — training uses 5y data; live inference fetches 500d, truncates to 250d for XGB
- SQLite state store — all persistent state in single WAL-mode database
- Parallel asset isolation — 15 AssetEngine instances execute independently via ThreadPoolExecutor

## Project Structure

```
features/              # Feature engineering
├── alpha_features.py  # Alpha feature factory (carry, momentum, z-score, vol regime, macro)
├── data_fetch.py      # yfinance ingestion (asset data + full OHLCV)
├── labels.py          # Triple-barrier labeling with vol-scaled barriers
├── regime_features.py # Hurst, KER, ADX, vol z-score, compression
├── archetypes.py      # 5 pure-feature archetype classifier
├── macro_narrative.py # Weekly LLM narrative governance
├── liquidity_regime.py# Volume/Amihud liquidity classification
├── fxstreet_fetcher.py# FXStreet scrape + LLM extraction
paper_trading/         # Live trading engine
├── engine.py          # PaperTradingEngine (orchestrator)
├── asset_engine.py    # AssetEngine (per-asset lifecycle)
├── portfolio_builder.py # Portfolio construction from YAML config
├── state_store.py     # SQLite-backed state store (5 tables, WAL mode)
├── inference/
│   ├── pipeline.py    # Live inference pipeline (truncation, async diagnostics)
│   ├── async_diagnostics.py  # Diagnostics daemon thread (off-hot-path)
│   └── training.py    # Binary XGBoost training pipeline
├── entry/             # Entry optimizer, policy, TP compiler
├── position/          # Position manager, dynamic SL/TP, scale-out
├── governance/        # Narrative, liquidity, regime, drift
├── execution/         # Paper broker, bridge
├── orchestrator/      # EngineOrchestrator, AssetActor, health state machine
├── shadow/            # Counterfactual replay engine
├── satellite/         # BTC satellite engine
├── ops/               # Data fetcher, diagnostics, tracer
├── api/               # REST API routes (state, trades, attribution, execution quality)
└── dashboard/         # React SPA frontend (Vite)
benchmarks/            # Hot-path microbenchmark harness
├── microbenchmark.py  # CLI: cold/warm cycles, asset × worker sweep, profiling
├── mock_data.py       # MockDataFixture (synthetic OHLCV at yfinance boundary)
└── README.md          # Reference numbers and usage
scripts/               # Research + ops scripts
├── walk_forward_backtest.py  # Multi-ticker walk-forward screening
├── score_tickers.py          # Promotion scoring
└── generate_promotion_report.py  # Report + YAML generation
walkforward/           # Screening results (fold ICs, summaries, promotion report)
shared/                # Pluggable strategy interfaces
monitoring/            # PSI drift, validity state machine
```

## Known Constraints

- Paper trading only (no live capital)
- Data limited to Yahoo Finance (no FRED in production)
- JPY/CHF crosses may show NaN prices on first cycle (incomplete daily bar)
- Ensemble system disabled by default (`ensemble.enabled: false` in config)
- 15 of 30 screened tickers classified RED (not promoted)

## License

MIT. Research system only. Not financial advice.

## Historical Context

This repository evolved through multiple research stages. Documentation of prior architectures is archived in `docs/archive/research_system_v1/`. Architecture Decision Records (ADRs) in `docs/adr/` document the reasoning history and are annotated with historical context notices where components no longer exist in production.
