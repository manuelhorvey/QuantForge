# Production System Spec v1.0

**QuantForge** — Cross-Sectional Factor Ranking & Paper Trading System

*Final clean architecture document. Defines what the system IS, not what it evolved from.*

---

## 1. System Identity

QuantForge is a **factor-based asset allocation system** with a **walk-forward validated screening pipeline**, **per-asset binary XGBoost models**, and a **paper trading execution layer**.

It is NOT a directional prediction system. It does NOT attempt to forecast price movements. It ranks assets on weak but positive IC signals and constructs a long/short equity-style basket.

### What the system produces

1. **Screening output**: Composite scores + promotion classifications (GREEN/YELLOW/RED) for 30+ tickers
2. **Per-asset models**: Binary XGBoost classifiers, one per promoted asset
3. **Live signals**: BUY/SELL/FLAT decisions every 5 minutes for 15 assets
4. **Portfolio allocation**: Risk-parity weighted long/short basket with governance overlay
5. **Execution traces**: Full attribution records (prediction, execution, exit, friction) per trade

### What the system does NOT do

- Does NOT predict price direction with consistent accuracy across all assets
- Does NOT use ensemble/regime routing in production (disabled by default)
- Does NOT use FRED macro data in the live pipeline
- Does NOT operate with live capital (paper trading only)
- Does NOT deploy every screened ticker (16/30 screened RED, not promoted)

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    SCREENING LAYER (offline, run once)                   │
│                                                                         │
│  30 tickers ──▶ walk_forward_backtest.py ──▶ score_tickers.py          │
│                   3y window, 1y step        composite score:            │
│                   5 folds, per-asset pt_sl    IC + hit rate + bidir     │
│                                              GREEN/YELLOW/RED           │
│                                              ──▶ promotion_report.json  │
└─────────────────────────────────────────────────────────────────────────┘
                              │  (top N assets promoted to live)
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    TRAINING LAYER (on-demand, per asset)                 │
│                                                                         │
│  yfinance ──▶ fetch_asset_data ──▶ alpha_features ──▶ triple_barrier    │
│   10y                           ~30 feature cols      label (pt_sl)     │
│                                                       binary reduce      │
│                                                       ──▶ XGBoost       │
│                                                       binary:logistic   │
│                                                       300 trees, d=2   │
│                                                       ──▶ .json model  │
└─────────────────────────────────────────────────────────────────────────┘
                              │  (model loaded by engine)
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    INFERENCE LAYER (per cycle, every 300s)               │
│  Parallel asset fetch (ThreadPoolExecutor, max_workers=8)               │
│                                                                         │
│  ┌─────────────┐   ┌──────────────────┐   ┌───────────────────┐        │
│  │ fetch_live  │──▶│ alpha+archetype  │──▶│ XGBoost predict   │        │
│  │ 500d OHLCV  │   │ features         │   │ binary → 3-col    │        │
│  │ (truncated  │   │                  │   │ proba expansion   │        │
│  │  to 250d    │   └──────────────────┘   └───────────────────┘        │
│  │  for XGB)   │         │                          │                  │
│  │ + realtime  │         │                          │                  │
│  │ price patch │         ▼                          ▼                  │
│  └─────────────┘   ┌───────────────┐   ┌─────────────────────┐         │
│                    │ AsyncDiagnos- │   │ Archetype           │         │
│                    │ tics Queue    │   │ classification     │         │
│                    │ (daemon)      │   │ 5 types from OHLCV  │         │
│                    │ → 8 heavy     │   └─────────────────────┘         │
│                    │   imports     │              │                    │
│                    │   off hotpath │              ▼                    │
│                    └───────────────┘   ┌─────────────────────┐         │
│                                        │ FixedThreshold     │         │
│                                        │ Strategy(0.45)     │         │
│                                        │ BUY/SELL/FLAT      │         │
│                                        └─────────────────────┘         │
│                                              │                          │
│                                              ▼                          │
│  ┌──────────────────┐   ┌──────────────────┐   ┌───────────────────┐   │
│  │ Position Manager │◀──│ EntryOptimizer   │◀──│ FixedThreshold   │   │
│  │ SL/TP/scale-out  │   │ + Policy Layer   │   │ Strategy(0.45)   │   │
│  │                  │   │ + _can_enter()   │   │ BUY/SELL/FLAT    │   │
│  └──────────────────┘   └──────────────────┘   └───────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    PORTFOLIO LAYER                                       │
│                                                                         │
│  15 assets, risk-parity weights (6.5–7.8% each)                        │
│  + BTC satellite (5% AUM cap, macro gate)                               │
│  SQLite state store (WAL mode): trades, attribution, equity_history     │
│  PaperBroker → StateStore → state.json + state.db → dashboard           │
│  7-layer governance overlay                                             │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Screening Layer

### 3.1 Walk-Forward Backtest

**Entry point**: `python scripts/walk_forward_backtest.py --tickers T1,T2,T3,...`

| Parameter | Value |
|---|---|
| Train window | 3 years |
| Step | 1 year |
| Folds | 5 (expanding) |
| Label | triple barrier with per-asset pt_sl |
| Feature window | 10 years from yfinance |
| Per-asset pt_sl | BTC-USD: (2.5, 3.0); others: (1.5, 2.0) |

**Output** (per ticker in `walkforward/`):
- Fold IC JSON (`{ticker}_fold_ic.json`)
- Signal parquet (`{ticker}_wf_signals.parquet`)
- Summary CSV (`{ticker}_wf_summary.csv`)

### 3.2 Scoring & Promotion

**Entry point**: `python scripts/score_tickers.py`

**Composite score formula**:
- IC normalized (weight: 30%)
- Hit rate normalized (weight: 25%)
- Bidirectionality (long rate + short rate, weight: 25%)
- Fold consistency (positive fold ratio, weight: 20%)

**Classification criteria**:
| Class | Requirements |
|---|---|
| **GREEN** (promote) | Score ≥ 65, IC > 0.03, hit rate > 0.40, FLAT < 70%, ≥50% positive folds, long & short > 5% |
| **YELLOW** (watch) | Score ≥ 35 or meets all criteria except one |
| **RED** (skip) | Below YELLOW thresholds |

**Output**: `walkforward/promotion_report.json`, `walkforward/PROMOTION_REPORT.md`, `walkforward/ticker_map.json`

---

## 4. Training Layer

### 4.1 Data Ingestion

All data sourced from yfinance (no FRED in production):

| Function | Returns | Period |
|---|---|---|
| `fetch_asset_data(name, ticker)` | (prices, rate_diffs, dxy, vix, spx, commodities) | 10y |
| `fetch_asset_ohlcv(ticker)` | DataFrame(open, high, low, close, volume) | 10y |

Rate_diffs are simulated from TNX yield with noise. All indices normalized to TZ-naive `datetime64[ns]`.

### 4.2 Feature Engineering

**Alpha features** (`features/alpha_features.py:build_alpha_features()`):

| Feature | Formula |
|---|---|
| `{asset}_carry_vol_adj` | Close return normalized by rolling vol |
| `{asset}_mom_21d` | `close.pct_change(21)` |
| `{asset}_mom_63d` | `close.pct_change(63)` |
| `{asset}_mom_126d` | `close.pct_change(126)` |
| `{asset}_mom_252d` | `close.pct_change(252)` |
| `{asset}_zscore_20` | `(close - SMA20) / std(close, 20)` |
| `{asset}_vol_ratio` | Short-term vol / long-term vol |
| `{asset}_dow_signal` | Day-of-week encoding |
| `dxy_mom_21/63` | DXY returns |
| `vix_mom_21/63` | VIX returns |
| `spx_mom_21/63` | SPX returns |
| `wti_mom_21/63` | WTI returns |

~30 feature columns per asset total.

### 4.3 Labeling

**Function**: `features/labels.py:triple_barrier_labels()`

1. Compute ATR-based barrier distances from `pt_sl = (tp_mult, sl_mult)`
2. Triple-barrier touch → {-1 (SELL), 0 (HOLD), 1 (BUY)}
3. Binary reduction: drop HOLD (0), map {-1, 1} → {0, 1}

**Default pt_sl**: (1.5, 2.0) for most assets; (2.5, 3.0) for BTC-USD.

### 4.4 Model Training

**Algorithm**: XGBoost `binary:logistic`
**Architecture**: Single binary XGBoost per asset (no ensemble, no routing)
**Hyperparameters**:

| Parameter | Value |
|---|---|
| n_estimators | 300 |
| max_depth | 2 |
| learning_rate | 0.02 |
| objective | `binary:logistic` |
| random_state | 42 |
| n_jobs | 1 |
| tree_method | `hist` |

**Training window**: Last 5 years of data (minimum 200 rows)
**Train/val split**: 80/20 chronological, stratified if min class count ≥ 2
**Serialization**: `model.save_model(path)` → `.json` format
**Post-training**:
- PSI baseline persist
- Optional meta-label model (XGBoost)
- Optional regime-conditional model (disabled by default)
- Feature importance + stability logging

### 4.5 Model Files

Location: `paper_trading/models/{asset_name}_model.json`
Format: XGBoost `.json` (not pickle)

---

## 5. Inference Layer

### 5.1 Pipeline (`paper_trading/inference/pipeline.py`)

**Frequency**: Every 300 seconds (configurable via `QUANTFORGE_REFRESH_INTERVAL`)

**Parallel execution**: 13 AssetEngine instances run via ThreadPoolExecutor (max_workers=8) in phases: REFRESH+Signal (parallel), VALIDITY (sequential), PORTFOLIO health, PERSIST.

**Steps**:
1. `fetch_live(ticker)` — 500 days OHLCV (yfinance `period="500d"`)
2. Normalize index to UTC TZ-naive date (fixes FX cross date shift)
3. `refresh_price()` — real-time price via `fast_info` or 5d fallback
4. `ffill()` close column
5. `fetch_asset_data()` — 10y close + macro (macro tickers batched into single `yf.download` call, TTL cache 300s)
6. `build_alpha_features()` — alpha_df (~30 feature cols)
7. `fetch_asset_ohlcv()` — 10y full OHLCV (no rate-limit sleep)
8. Archetype features from OHLCV: ema_spread, ADX(14), RSI(14), BB_zscore(20)
9. PSI drift check (rolling 21d vs baseline; skipped first cycle)
10. Inference truncation: 500d → 250d via `_truncate_to_window()`, with behavioral validation (window size, date range, NaN ratio)
11. Model hot-swap validation: checks object identity change (`model is not last_model`) and re-validates full inference chain on swap
12. XGBoost predict → 3-column proba expansion:
    ```python
    if raw.shape[1] == 2:  # binary model
        proba = np.column_stack([1.0 - raw[:,1], zeros, raw[:,1]])
    ```
13. Optional regime ensemble blend (disabled unless `ensemble.enabled: true`)
14. Optional meta-label inference
15. `FixedThresholdStrategy(threshold=0.45)` → SignalType (BUY/SELL/FLAT)
16. Archetype classification → `TradeDecision(close_price, confidence, probs, ...)`
17. DiagnosticsSnapshot enqueues model/feature snapshots off hot path via async daemon consumer (8 heavy imports removed from inference thread)
18. `_apply_decision()` → EntryOptimizer → ExecutionPolicyLayer → PositionManager

### 5.2 Signal Contract

| Condition | Result |
|---|---|
| `prob_long > 0.45` AND `prob_short <= 0.45` | BUY |
| `prob_short > 0.45` AND `prob_long <= 0.45` | SELL |
| Both > 0.45 | BUY (long wins by order) |
| Neither > 0.45 | FLAT |

### 5.3 Archetype Classification

Computed from OHLCV feature vector (no model inference):

| Archetype | Triggers |
|---|---|
| MOMENTUM_IGNITION | Rate-of-change acceleration + EMA structure |
| MEAN_REVERSION | Overextended BB + RSI extremes |
| BREAKOUT_TEST | KER + ADX + vol contraction |
| VOL_EXPANSION | Vol z-score spike + compression release |
| UNKNOWN | Default fallback |

---

## 6. Portfolio Layer

### 6.1 Current Composition

**15 assets** promoted from 30-ticker walk-forward screening, risk-parity weighted:

| Asset | Ticker | Allocation | sl_mult | tp_mult | Score |
|---|---|---|---|---|---|
| BTCUSD | BTC-USD | 6.5% | 3.0 | 2.5 | 80.9 |
| EURGBP | EURGBP=X | 6.5% | 2.0 | 1.5 | 69.0 |
| GC | GC=F | 6.5% | 2.0 | 1.5 | 66.7 |
| NZDCHF | NZDCHF=X | 6.5% | 2.0 | 1.5 | 70.0 |
| CHFJPY | CHFJPY=X | 6.5% | 2.0 | 1.5 | YELLOW |
| CADJPY | CADJPY=X | 6.5% | 2.0 | 1.5 | YELLOW |
| USDCHF | USDCHF=X | 6.5% | 2.0 | 1.5 | YELLOW |
| EURJPY | EURJPY=X | 6.5% | 2.0 | 1.5 | YELLOW |
| EURCAD | EURCAD=X | 6.5% | 2.0 | 1.5 | YELLOW |
| AUDCHF | AUDCHF=X | 6.5% | 2.0 | 1.5 | YELLOW |
| USDJPY | USDJPY=X | 6.5% | 2.0 | 1.5 | YELLOW |
| USDCAD | USDCAD=X | 6.5% | 2.0 | 1.5 | YELLOW |
| GBPCHF | GBPCHF=X | 6.5% | 2.0 | 1.5 | YELLOW |
| ES | ES=F | 7.7% | 2.0 | 2.5 | 76.9 |
| NQ | NQ=F | 7.8% | 2.0 | 2.5 | 67.9 |

**BTC satellite**: 5% AUM cap, vol target 40%, macro-gated entry via `HighVolSatellite`.

### 6.2 Position Sizing

**Base**: Equal-risk weights via `shared/sizing.py:compute_equal_risk_weights()`
**Capital utilization**: Default 0.95
**Size scalar chain**:
```
final_size = base × governance_scalar × meta_confidence_scalar
```

### 6.3 Governance Layers

| Layer | Frequency | Effect |
|---|---|---|
| Validity state machine | Per tick | Exposure 0–100% |
| Feature stability | Per retrain | Validity penalty |
| Meta-labeling (XGBoost) | Per signal | Size scalar [0–1] |
| Macro narrative | Weekly | SL +10%, size −20% |
| Liquidity regime | Per signal | SL +15/30%, size −15/30%, halt |
| PSI drift | Per cycle | Validity penalty, halt at 3+ SEVERE |
| Portfolio drawdown | Per cycle | Circuit breaker at −15% |

---

## 7. Data Contract

### 7.1 Sources
| Source | Data | Notes |
|---|---|---|
| yfinance | Daily OHLCV for all assets | Single source of truth |
| yfinance | DXY (DX-Y.NYB), VIX (^VIX), SPX (^GSPC), WTI (CL=F), TNX (^TNX) | Macro via yfinance only |
| FRED | Not used in production | Historical research only |

### 7.2 Index Convention

All date indices are `datetime64[ns]` at daily resolution, TZ-naive.
The pipeline normalizes `fetch_live()` output:
```python
df.index = pd.to_datetime(df.index.tz_convert("UTC").date)
```

### 7.3 Caching

In-memory TTL cache per download type:
- OHLCV: 60s TTL
- Realtime price: 5s TTL
- Macro data (DXY, VIX, SPX, WTI, TNX): 300s TTL, batched into single `yf.download` call

---

## 8. System Invariants

1. **No train/serve skew**: Same alpha feature builder in training and inference
2. **TZ-naive date alignment**: All pipeline stages use UTC dates
3. **Per-asset model independence**: Separate binary XGBoost per asset
4. **Walk-forward validated**: Every promoted asset passes expanding window backtest
5. **Binary signal only**: HOLD dropped; model trains on {-1, 1}
6. **Single entry authority**: All entries through `_can_enter()`
7. **Frozen execution contract**: PolicyDecision → FillResult → AttributionRecord immutable chain
8. **Worst-wins governance**: Most negative penalty applied, not averaged
9. **Per-asset pt_sl**: Barrier geometry from config, applied label-time and runtime
10. **.json serialization**: No pickle in production
11. **Inference truncation symmetry**: Training uses 5y data; live inference fetches 500d, truncates to 250d for XGBoost (matching training window)
12. **SQLite state store**: All persistent state in single WAL-mode database; legacy JSON/parquet files are read-only fallbacks
13. **Parallel asset isolation**: 13 AssetEngine instances execute independently via ThreadPoolExecutor; health monitor tracks per-asset DEGRADED/HALTED states independently

---

## 9. File Map

| Path | Role |
|---|---|
| `configs/paper_trading.yaml` | Production config (15 assets, params) |
| `features/alpha_features.py` | Alpha feature factory |
| `features/data_fetch.py` | YFinance data ingestion |
| `features/labels.py` | Triple-barrier labeling |
| `features/archetypes.py` | Archetype classifier |
| `features/regime_features.py` | Regime detection features |
| `paper_trading/engine.py` | Engine orchestrator |
| `paper_trading/asset_engine.py` | Per-asset lifecycle |
| `paper_trading/portfolio_builder.py` | Portfolio from config |
| `paper_trading/state_store.py` | SQLite state persistence (5 tables, WAL mode) |
| `paper_trading/inference/pipeline.py` | Live inference pipeline |
| `paper_trading/inference/training.py` | Binary XGBoost training |
| `paper_trading/inference/async_diagnostics.py` | Deferred diagnostics (daemon consumer queue) |
| `paper_trading/orchestrator/engine.py` | Parallel asset orchestration (ThreadPoolExecutor) |
| `paper_trading/orchestrator/actor.py` | Per-asset actor with health state |
| `paper_trading/orchestrator/health.py` | Portfolio-level health monitor + circuit breaker |
| `paper_trading/models/` | Trained models (.json) |
| `benchmarks/microbenchmark.py` | Isolated performance benchmark (`--state-dir`) |
| `scripts/walk_forward_backtest.py` | Multi-ticker screening |
| `scripts/score_tickers.py` | Promotion scoring |
| `scripts/generate_promotion_report.py` | Report + YAML generation |
| `walkforward/` | Screening results |
| `LIVE_CONTRACT.md` | Immutable system contract |

---

## 10. Known Constraints

1. **Paper trading only** — no live capital execution
2. **Yahoo Finance single source** — all data via yfinance, including macro
3. **FX cross price NaN on first cycle** — incomplete daily bar; resolves after next cycle with full bar
4. **Ensemble disabled** — `ensemble.enabled: false` in config; experimental feature
5. **15/30 tickers RED** — not promoted; reflects weak IC for most FX pairs
6. **No FRED** — macro derived from yfinance tickers only; no FRED API dependency in production
7. **JPY/CHF cross TZ issue** — fixed via UTC normalization in pipeline
8. **Attribution table schema gap** — `attribution` table in SQLite lacks friction columns (`friction_fill_qty_ratio`, `friction_gap_fill`, `friction_partial_fill`, `friction_latency_bars`) that exist in `trades` table. Frontend uses nullish defaults (`??`) as workaround.
9. **Benchmark isolation** — `microbenchmark.py --state-dir` uses temp directory by default; must never point at production `data/live/`

---

*Spec version 1.0 — May 2026*
*Supersedes all prior documentation. Production code is truth.*
