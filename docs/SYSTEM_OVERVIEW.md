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

```text
Research Universe (36+ assets)
        ↓
Walk-Forward Validation (expanding window)
        ↓
Asset Selection (GREEN / YELLOW / RED)
        ↓
Per-Asset Training (XGBoost, per-asset depth)
        ↓
Live Inference
        ↓
Governance Filters (7 layers)
        ↓
Execution & Positioning (MT5 or PaperBroker)
        ↓
Persistence & Replay
        ↓
Monitoring & Attribution
```

---

# System Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│                       RESEARCH / SCREENING                          │
│                                                                     │
│  36+ tickers                                                        │
│      ↓                                                              │
│  trade_analysis.py (walk-forward style)                             │
│      ↓                                                              │
│  walk_forward_backtest.py                                           │
│      ↓                                                              │
│  score_tickers.py                                                   │
│      ↓                                                              │
│  Promotion to dashboard                                             │
│                                                                     │
│  Output:                                                            │
│  - per-asset SL/TP/depth calibration                                │
│  - GREEN / YELLOW / RED states                                      │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    MODEL TRAINING                                   │
│                                                                     │
│  fetch_asset_data()                                                 │
│      ↓                                                              │
│  build_features() (per-asset from FEATURE_REGISTRY)                 │
│      ↓                                                              │
│  triple_barrier_labels()                                            │
│      ↓                                                              │
│  binary reduction (drop HOLD)                                       │
│      ↓                                                              │
│  XGBoost binary:logistic (per-asset max_depth)                      │
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
│  build_features()                                                   │
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
| Per-asset model depth       | `max_depth` configured per-asset (2–5), not global             |

---

# Execution Lifecycle

## 1. Research & Asset Selection

The offline research stage evaluates a universe of 36+ assets using expanding-window walk-forward validation.

### Validation Structure

* 3-year rolling training window
* 1-year forward evaluation (or 5-year full validation)
* per-asset SL/TP/depth calibration
* IC + hit-rate scoring
* directional consistency weighting

Assets are classified into GREEN / YELLOW / RED. Only promoted assets enter the live portfolio.

---

## 2. Model Training

Each promoted asset trains an independent XGBoost model.

### Training Pipeline

```text
fetch_asset_data()
        ↓
build_features() (per-asset from FEATURE_REGISTRY)
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
| Max Depth     | per-asset (2–5)   |
| Learning Rate | 0.02              |

Per-asset max_depth from `configs/paper_trading.yaml`. No shared multi-asset model exists.

---

# Live Inference Pipeline

The live engine executes every 300 seconds.

## Runtime Pipeline

```text
1. Fetch 500d OHLCV
2. Normalize timestamps
3. Refresh latest price
4. Fetch macro data
5. Build features (per-asset from FEATURE_REGISTRY)
6. Fetch full OHLCV
7. Compute archetype features
8. Validate inference truncation
9. Validate model hot-swap integrity
10. Run XGBoost inference
11. Expand binary probabilities
12. Apply threshold strategy (THR=0.45)
13. Generate TradeDecision
14. Route through governance
15. Execute position lifecycle
```

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

---

# Failure Isolation

Each asset executes independently. Failures in data ingestion, inference, governance, diagnostics, or execution cannot halt the global engine. Emergency portfolio circuit breakers activate when halt ratios exceed configured thresholds.

---

# Component Responsibilities

## Feature Engineering (`features/`)

| Module                | Purpose                             |
| --------------------- | ----------------------------------- |
| `builder.py`          | Per-asset feature construction      |
| `registry.py`         | Feature contracts (36 tickers)      |
| `labels.py`           | Triple-barrier labeling             |
| `archetypes.py`       | Market structure classification     |
| `macro_narrative.py`  | Weekly macro narrative overlays     |
| `liquidity_regime.py` | Liquidity classification            |
| `contract.py`         | Feature contract dataclass          |
| `fxstreet_fetcher.py` | FXStreet → LLM narrative extraction |

---

## Paper Trading Engine (`paper_trading/`)

| Component                | Role                        |
| ------------------------ | --------------------------- |
| `PaperTradingEngine`     | Top-level orchestrator      |
| `AssetEngine`            | Per-asset lifecycle         |
| `AssetInferencePipeline` | Live inference              |
| `AssetTrainingPipeline`  | Training pipeline           |
| `PortfolioBuilder`       | Asset registry construction |
| `StateStore`             | SQLite persistence          |
| `EntryOptimizer`         | Entry conditioning          |
| `ExecutionPolicyLayer`   | Unified execution routing   |
| `PositionManager`        | Position lifecycle          |
| `PaperBroker`            | Simulated fills             |
| `ExecutionBridge`        | Slippage + impact           |
| `ShadowSLTPEngine`       | Counterfactual replay       |
| `AttributionCollector`   | Attribution pipeline        |
| `EngineOrchestrator`     | Parallel orchestration      |
| `AssetActor`             | Asset execution wrapper     |
| `HealthMonitor`          | Portfolio-level health      |

---

# Configuration

`configs/paper_trading.yaml` controls:
* capital allocation,
* rebalance frequency,
* per-asset SL/TP/depth,
* governance layers,
* orchestrator settings,
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
| Walk-forward screening    | `python backtests/trade_analysis.py`          |
| Score tickers             | `python scripts/score_tickers.py`             |
| Generate promotion report | `python scripts/generate_promotion_report.py` |
| Start engine + dashboard  | `./monitor_all`                               |
| Retrain all assets        | `python scripts/train_all_assets.py`          |
| Run microbenchmark        | `python benchmarks/microbenchmark.py`         |
| Run tests                 | `pytest tests/ -q --tb=short`                 |

Dashboard URL: http://127.0.0.1:5000

---

# Known Constraints

* Paper trading only
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
