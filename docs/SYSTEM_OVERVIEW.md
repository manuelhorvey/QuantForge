# QuantForge — System Overview

Architecture, component responsibilities, execution lifecycle, and persistence model for the QuantForge cross-sectional research and paper trading platform.

---

# System Philosophy

QuantForge is designed around a simple operational principle:

> robustness matters more than alpha complexity.

The system prioritizes:

* deterministic execution,
* replay-oriented persistence,
* walk-forward validation,
* train/serve symmetry,
* per-asset isolation,
* governance layering,
* and operational observability

over maximizing in-sample returns.

The repository intentionally treats trading infrastructure as a distributed state-management problem rather than purely a signal-generation problem.

---

# High-Level Architecture

```text id="z2l0cm"
Research Universe
        ↓
Walk-Forward Validation
        ↓
Asset Selection
        ↓
Per-Asset Training
        ↓
Live Inference
        ↓
Governance Filters
        ↓
Execution & Positioning
        ↓
Persistence & Replay
        ↓
Monitoring & Attribution
```

---

# System Architecture

```text id="0qfg98"
┌─────────────────────────────────────────────────────────────────────┐
│                       RESEARCH / SCREENING                          │
│                                                                     │
│  30+ tickers                                                        │
│      ↓                                                              │
│  walk_forward_backtest.py                                           │
│      ↓                                                              │
│  score_tickers.py                                                   │
│      ↓                                                              │
│  generate_promotion_report.py                                       │
│      ↓                                                              │
│  promotion_report.json                                              │
│                                                                     │
│  Output:                                                            │
│  - fold ICs                                                         │
│  - directional consistency                                          │
│  - GREEN / YELLOW / RED states                                      │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    MODEL TRAINING                                   │
│                                                                     │
│  fetch_asset_data()                                                 │
│      ↓                                                              │
│  build_alpha_features()                                             │
│      ↓                                                              │
│  triple_barrier_labels()                                            │
│      ↓                                                              │
│  binary reduction                                                   │
│      ↓                                                              │
│  XGBoost binary:logistic                                            │
│      ↓                                                              │
│  model persistence + PSI baseline                                   │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    LIVE INFERENCE                                   │
│                                                                     │
│  Parallel asset execution                                           │
│  ThreadPoolExecutor(max_workers=8)                                  │
│                                                                     │
│  fetch_live()                                                       │
│      ↓                                                              │
│  build_alpha_features()                                             │
│      ↓                                                              │
│  XGBoost inference                                                  │
│      ↓                                                              │
│  archetype classification                                           │
│      ↓                                                              │
│  EntryOptimizer                                                     │
│      ↓                                                              │
│  ExecutionPolicyLayer                                               │
│      ↓                                                              │
│  PositionManager                                                    │
│                                                                     │
│  Async diagnostics run off-thread                                   │
│  via daemon consumer queue                                          │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    STATE PERSISTENCE                                │
│                                                                     │
│  SQLite WAL-mode persistence                                        │
│                                                                     │
│  - trades                                                           │
│  - attribution                                                      │
│  - shadow_trades                                                    │
│  - confidence_buckets                                               │
│  - equity_history                                                   │
│                                                                     │
│  Replay-oriented append semantics                                   │
│  with deterministic reconstruction support                          │
└─────────────────────────────────────────────────────────────────────┘
```

---

# Core Architectural Properties

| Property                    | Description                                                    |
| --------------------------- | -------------------------------------------------------------- |
| Walk-forward validated      | Assets must pass expanding-window validation before deployment |
| Per-asset isolation         | Every asset runs independently with its own model lifecycle    |
| Replay-oriented persistence | Persistent state supports deterministic reconstruction         |
| Immutable execution chain   | PolicyDecision → FillResult → AttributionRecord                |
| Governance-first execution  | Exposure controlled by layered governance                      |
| Failure isolation           | Asset failures cannot halt the global engine                   |
| Single entry authority      | All entries route through `_can_enter()`                       |
| Train/serve symmetry        | Shared feature generation between training and inference       |
| Parallel orchestration      | Assets execute concurrently through isolated actors            |

---

# Execution Lifecycle

## 1. Research & Asset Selection

The offline research stage evaluates a universe of 30+ assets using expanding-window walk-forward validation.

### Validation Structure

* 3-year rolling training window
* 1-year forward evaluation
* 5-fold walk-forward process
* per-asset PT/SL calibration
* IC + hit-rate scoring
* directional consistency weighting
* bidirectionality evaluation

Assets are classified into:

* GREEN
* YELLOW
* RED

Only promoted assets enter the live portfolio.

---

## 2. Model Training

Each promoted asset trains an independent binary XGBoost model.

### Training Pipeline

```text id="bh0b5h"
fetch_asset_data()
        ↓
build_alpha_features()
        ↓
triple_barrier_labels()
        ↓
drop HOLD states
        ↓
binary reduction {0,1}
        ↓
XGBoost binary:logistic
        ↓
persist model + PSI baseline
```

### Model Configuration

| Parameter     | Value             |
| ------------- | ----------------- |
| Objective     | `binary:logistic` |
| Trees         | 300               |
| Max Depth     | 2                 |
| Learning Rate | 0.02              |

No shared multi-asset model exists.

This intentionally isolates:

* feature drift,
* calibration instability,
* regime degradation,
* and inference failures

to individual assets.

---

# Feature Engineering

## Alpha Features

Implemented in `features/alpha_features.py`.

### Feature Families

* Volatility-adjusted carry
* Multi-horizon momentum:

  * 21d
  * 63d
  * 126d
  * 252d
* Z-score mean reversion
* Volatility regime ratio
* Day-of-week effects
* Cross-asset macro momentum:

  * DXY
  * VIX
  * SPX
  * WTI

Macro data is batch-fetched through a single `yf.download()` call with TTL caching.

---

## Market Structure Features

Inference-only archetype features derived from OHLCV:

* EMA spread
* ADX(14)
* RSI(14)
* Bollinger z-score

Used for:

* execution conditioning,
* trade timing,
* and regime-aware management.

---

# Live Inference Pipeline

The live engine executes every 300 seconds.

## Runtime Pipeline

```text id="2u8l08"
1. Fetch 500d OHLCV
2. Normalize timestamps
3. Refresh latest price
4. Fetch macro data
5. Build alpha features
6. Fetch full OHLCV
7. Compute archetype features
8. Validate inference truncation
9. Validate model hot-swap integrity
10. Run XGBoost inference
11. Expand binary probabilities
12. Apply threshold strategy
13. Generate TradeDecision
14. Route through governance
15. Execute position lifecycle
```

---

# Runtime Optimizations

QuantForge contains multiple optimizations designed to reduce hot-path latency and runtime instability.

## Optimizations

* Vectorized triple-barrier labeling
* Broadcast-based inference operations
* Parallel asset execution
* Async diagnostics off hot path
* TTL macro cache
* SQLite WAL persistence
* Inference truncation validation
* Model object-identity hot-swap checks
* Heavy-import isolation via daemon queue

---

# Parallel Orchestration

Live assets execute through isolated actors managed by `EngineOrchestrator`.

## Orchestration Phases

```text id="8x8xv4"
REFRESH + SIGNAL (parallel)
            ↓
VALIDITY CHECKS
            ↓
PORTFOLIO HEALTH
            ↓
STATE PERSISTENCE
```

Each `AssetActor` tracks:

* health state,
* execution timing,
* exposure,
* and degradation status.

---

# Governance Architecture

QuantForge uses independently configurable governance layers with worst-wins aggregation.

## Governance Layers

| Layer                  | Scope      | Effect                    |
| ---------------------- | ---------- | ------------------------- |
| Exposure state machine | Per asset  | Exposure scaling          |
| Feature stability      | Per asset  | Validity penalties        |
| Meta-labeling          | Per signal | Position scalar           |
| Macro regime overlay   | Global     | Exposure + SL adjustments |
| Liquidity regime       | Per asset  | Throttling + halts        |
| PSI drift monitor      | Per asset  | Penalties + halts         |
| Portfolio drawdown     | Global     | Portfolio throttling      |

---

# Persistence Model

Persistent state is stored in SQLite WAL mode.

## Persistent Tables

| Table                | Purpose               |
| -------------------- | --------------------- |
| `trades`             | Trade records         |
| `attribution`        | Attribution outputs   |
| `shadow_trades`      | Counterfactual replay |
| `confidence_buckets` | Confidence analytics  |
| `equity_history`     | Equity curve history  |

## Persistence Properties

* append-oriented writes
* replay-oriented semantics
* deterministic recovery support
* periodic WAL checkpointing
* backward-compatible JSON snapshots
* SHA-256 checksummed cold state (tamper detection via `.sha256` sidecar)

---

# Failure Isolation

Each asset executes independently.

Failures in:

* data ingestion,
* inference,
* governance,
* diagnostics,
* or execution

cannot halt the global engine.

Emergency portfolio circuit breakers activate when halt ratios exceed configured thresholds.

---

# Component Responsibilities

## Feature Engineering (`features/`)

| Module                | Purpose                             |
| --------------------- | ----------------------------------- |
| `alpha_features.py`   | Alpha feature generation            |
| `data_fetch.py`       | YFinance ingestion + macro batching |
| `labels.py`           | Triple-barrier labeling             |
| `regime_features.py`  | Regime feature computation          |
| `archetypes.py`       | Market structure classification     |
| `macro_narrative.py`  | Weekly macro narrative overlays     |
| `liquidity_regime.py` | Liquidity classification            |
| `contract.py`         | Immutable feature contracts         |
| `fxstreet_fetcher.py` | FXStreet → LLM narrative extraction |

---

## Paper Trading Engine (`paper_trading/`)

| Component                | Role                        |
| ------------------------ | --------------------------- |
| `PaperTradingEngine`     | Top-level orchestrator      |
| `AssetEngine`            | Per-asset lifecycle         |
| `AssetInferencePipeline` | Live inference              |
| `AssetTrainingPipeline`  | Training pipeline           |
| `DiagnosticsSnapshot`    | Deferred diagnostics        |
| `PortfolioBuilder`       | Asset registry construction |
| `StateStore`             | SQLite persistence          |
| `EntryOptimizer`         | Entry conditioning          |
| `ExecutionPolicyLayer`   | Unified execution routing   |
| `PositionManager`        | Position lifecycle          |
| `PaperBroker`            | Simulated fills             |
| `ExecutionBridge`        | Slippage + impact           |
| `ShadowSLTPEngine`       | Counterfactual replay       |
| `AttributionCollector`   | Attribution pipeline        |
| `HighVolSatellite`       | BTC opportunistic sleeve    |
| `EngineOrchestrator`     | Parallel orchestration      |
| `AssetActor`             | Asset execution wrapper     |
| `HealthMonitor`          | Portfolio-level health      |

---

# Configuration

`configs/paper_trading.yaml` controls:

* capital allocation,
* rebalance frequency,
* per-asset SL/TP geometry,
* governance layers,
* orchestrator settings,
* ensemble configuration,
* narrative overlays,
* and liquidity controls.

---

# Data Persistence

| Store                 | Format     | Purpose                    |
| --------------------- | ---------- | -------------------------- |
| `state.json`          | JSON       | Dashboard snapshot         |
| `state.db`            | SQLite WAL | Persistent execution state |
| `trade_outcomes.json` | JSON       | Cached aggregate analytics |

---

# Key Entry Points

| Action                    | Command                                       |
| ------------------------- | --------------------------------------------- |
| Walk-forward screening    | `python scripts/walk_forward_backtest.py`     |
| Score tickers             | `python scripts/score_tickers.py`             |
| Generate promotion report | `python scripts/generate_promotion_report.py` |
| Start engine + dashboard  | `./monitor_all` or `python main.py`           |
| Retrain all assets        | `python scripts/train_all_assets.py`          |
| Regenerate baseline       | `make snapshot`                               |
| Pin + install deps        | `make deps`                                   |
| Run microbenchmark        | `python benchmarks/microbenchmark.py`         |
| Run tests                 | `pytest tests/ -q --tb=short`                 |

Dashboard URL:

```text id="q8n6hf"
http://127.0.0.1:5000
```

---

# Known Constraints

* Paper trading only
* Yahoo Finance dependency (with automated quality monitoring: stale-data + NaN gap detection)
* No live brokerage integration
* Ensemble disabled by default
* Some FX crosses may produce incomplete first-cycle bars
* Macro data sourced entirely from Yahoo Finance

---

# Future Work

* Deterministic full-day replay reconstruction
* Event-sequence verification tooling
* Distributed multi-engine orchestration
* Extended execution quality analytics
* Portfolio-level regime optimization
* Broker abstraction layer
* Advanced replay visualization tooling
