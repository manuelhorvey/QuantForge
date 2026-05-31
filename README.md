# QuantForge

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Status](https://img.shields.io/badge/status-paper%20trading-green)
![WalkForward](https://img.shields.io/badge/walk--forward-30%20assets%20screened-success)
![Portfolio](https://img.shields.io/badge/portfolio-15%20live%20assets-blue)
[![codecov](https://codecov.io/gh/manuelhorvey/QuantForge/graph/badge.svg)](https://codecov.io/gh/manuelhorvey/QuantForge)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

Cross-sectional multi-asset research and paper trading engine with walk-forward asset selection, per-asset machine learning models, governance-driven execution, and replay-oriented state architecture.

---

# Design Philosophy

QuantForge is built around a simple principle:

> alpha is fragile; infrastructure robustness matters more.

The system prioritizes:

* walk-forward validation,
* deterministic execution,
* train/serve symmetry,
* replayability,
* governance layering,
* per-asset isolation,
* and operational observability

over maximizing in-sample returns.

Every promoted asset must survive expanding-window validation before entering the live paper portfolio. Runtime execution is treated as a state-machine and systems-engineering problem rather than purely a signal-generation problem.

---

# System Lifecycle

```text
Research Universe
        ↓
Walk-Forward Screening
        ↓
Asset Selection
        ↓
Per-Asset Model Training
        ↓
Live Inference
        ↓
Governance Filters
        ↓
Execution
        ↓
State Persistence + Replay
```

---

# Core Properties

* Walk-forward validated before deployment
* Per-asset model independence
* Deterministic execution contracts
* Replay-oriented state persistence
* Governance-first exposure control
* Parallel isolated asset engines
* Train/serve feature symmetry
* Immutable execution attribution chain
* Single centralized entry authority
* Failure-domain isolation across assets

---

# System Overview

QuantForge operates as a factor-style allocation and execution platform.

A universe of 30+ FX, commodity, equity-index, and crypto tickers is screened using expanding-window walk-forward backtests. Assets are scored on directional consistency, information coefficient, hit rate, and regime robustness before being promoted into the live paper portfolio.

Each promoted asset runs an independent binary XGBoost model conditioned on:

* volatility-adjusted carry,
* multi-horizon momentum,
* z-score reversion,
* volatility regime behavior,
* and cross-asset macro momentum.

Execution is governed by a seven-layer risk and validity framework with archetype-aware trade management.

```text
┌────────────────┐
│ Research       │
│ Universe       │
│ 30+ Assets     │
└──────┬─────────┘
       │
       ▼
┌────────────────┐
│ Walk-Forward   │
│ Validation     │
│ 5-Fold Expanding
│ Window Testing │
└──────┬─────────┘
       │
       ▼
┌────────────────┐
│ Asset          │
│ Selection      │
│ GREEN/YELLOW   │
│ RED            │
└──────┬─────────┘
       │
       ▼
┌────────────────┐
│ Live Inference │
│ Per-Asset      │
│ Binary XGBoost │
└──────┬─────────┘
       │
       ▼
┌────────────────┐
│ Governance     │
│ + Execution    │
│ + Positioning  │
└──────┬─────────┘
       │
       ▼
┌────────────────┐
│ Portfolio      │
│ Construction   │
│ Equal-Risk     │
└────────────────┘
```

---

# Current Portfolio

15 live paper-traded assets promoted from the research universe.

| Asset  | Ticker   | State  | Allocation | sl_mult | tp_mult | Walk-Forward Score | IC     |
| ------ | -------- | ------ | ---------- | ------- | ------- | ------------------ | ------ |
| BTCUSD | BTC-USD  | GREEN  | 6.5%       | 3.0     | 2.5     | 80.9               | 0.2264 |
| EURGBP | EURGBP=X | GREEN  | 6.5%       | 2.0     | 1.5     | 69.0               | 0.1104 |
| GC     | GC=F     | GREEN  | 6.5%       | 2.0     | 1.5     | 66.7               | 0.1270 |
| NZDCHF | NZDCHF=X | GREEN  | 6.5%       | 2.0     | 1.5     | 70.0               | 0.1080 |
| CHFJPY | CHFJPY=X | YELLOW | 6.5%       | 2.0     | 1.5     | —                  | —      |
| CADJPY | CADJPY=X | YELLOW | 6.5%       | 2.0     | 1.5     | —                  | —      |
| USDCHF | USDCHF=X | YELLOW | 6.5%       | 2.0     | 1.5     | —                  | —      |
| EURJPY | EURJPY=X | YELLOW | 6.5%       | 2.0     | 1.5     | —                  | —      |
| EURCAD | EURCAD=X | YELLOW | 6.5%       | 2.0     | 1.5     | —                  | —      |
| AUDCHF | AUDCHF=X | YELLOW | 6.5%       | 2.0     | 1.5     | —                  | —      |
| USDJPY | USDJPY=X | YELLOW | 6.5%       | 2.0     | 1.5     | —                  | —      |
| USDCAD | USDCAD=X | YELLOW | 6.5%       | 2.0     | 1.5     | —                  | —      |
| GBPCHF | GBPCHF=X | YELLOW | 6.5%       | 2.0     | 1.5     | —                  | —      |
| ES     | ES=F     | GREEN  | 7.7%       | 2.0     | 2.5     | 76.9               | 0.1273 |
| NQ     | NQ=F     | GREEN  | 7.8%       | 2.0     | 2.5     | 67.9               | 0.0932 |

### BTC Opportunistic Sleeve

BTC exposure is managed independently through a high-volatility satellite engine:

* 5% AUM cap
* 40% volatility target
* macro-gated participation
* crisis-regime suppression
* portfolio-aware exposure throttling

Managed via `HighVolSatellite`.

---

# Why Binary Classification?

QuantForge intentionally reduces the prediction problem to directional participation rather than return magnitude estimation.

The system optimizes for:

* directional consistency,
* ranking stability,
* calibration simplicity,
* execution compatibility,
* and governance composability

rather than precise return forecasting.

HOLD states are intentionally removed during training to avoid ambiguous class boundaries and unstable low-confidence behavior.

---

# Research & Validation Pipeline

## Walk-Forward Validation

All assets are evaluated using expanding-window walk-forward testing:

* 3-year training window
* 1-year forward test
* 5 folds
* per-asset PT/SL calibration
* IC + hit-rate scoring
* consistency weighting
* bidirectionality validation

Only promoted assets enter the live portfolio.

---

# Feature Engineering

## Alpha Features

Built in `features/alpha_features.py`.

Primary feature families:

* Volatility-adjusted carry
* Multi-horizon momentum (21 / 63 / 126 / 252d)
* Z-score mean reversion
* Volatility regime ratio
* Day-of-week effects
* Cross-asset macro momentum:

  * DXY
  * VIX
  * SPX
  * WTI

Macro data is batch-fetched via a single `yf.download` request with TTL caching.

---

## Market Structure Regimes

Inference-only archetype features derived from OHLCV:

* EMA spread
* ADX(14)
* RSI(14)
* Bollinger z-score

Used for:

* execution conditioning,
* trade management,
* and regime-aware positioning.

---

# Model Architecture

Each asset runs an independent binary XGBoost model.

```text
Objective:       binary:logistic
Trees:           300
Depth:           2
LR:              0.02
Serialization:   XGBoost native .json (not pickle)
Checksummed:     cold_state.pkl via SHA-256
```

No shared multi-asset model exists.

This intentionally isolates:

* feature drift,
* regime instability,
* calibration failures,
* and execution degradation

to individual assets.

---

# Inference Pipeline

```text
1. Fetch live OHLCV
2. Refresh latest price
3. Fetch macro data
4. Build alpha features
5. Fetch full OHLCV
6. Validate truncation behavior
7. Validate model hot-swap integrity
8. Run XGBoost inference
9. Classify market structure
10. Apply execution strategy
11. Enqueue async diagnostics
12. Route through governance
```

---

# Execution Architecture

```text
TradeDecision
      ↓
EntryOptimizer
      ↓
ExecutionPolicyLayer
      ↓
_can_enter()
      ↓
PositionManager
      ↓
Attribution Engine
```

## Key Invariants

### Single Entry Authority

All entry paths route through `_can_enter()`.

No component may bypass centralized admission control.

This prevents:

* inconsistent exposure logic,
* duplicate entries,
* governance desynchronization,
* and state divergence.

---

### Immutable Execution Contract

Execution follows a frozen lifecycle:

```text
PolicyDecision
    → FillResult
        → AttributionRecord
```

Execution artifacts are append-only and replay-safe.

---

### Train/Serve Symmetry

The same alpha feature builder is used in both:

* training,
* and live inference.

This eliminates train/serve skew.

---

### Replay-Oriented Persistence

Persistent state is stored in SQLite WAL mode with append-oriented semantics.

The architecture is designed for:

* deterministic replay,
* state reconstruction,
* execution auditing,
* and event-sequence validation.

Legacy JSON snapshots remain supported for backward compatibility.

---

# Governance Framework

QuantForge uses independently configurable governance layers with worst-wins aggregation.

| Layer                  | Frequency   | Scope     | Effect                    |
| ---------------------- | ----------- | --------- | ------------------------- |
| Exposure state machine | Per tick    | Per asset | Exposure scaling          |
| Feature stability      | Per retrain | Per asset | Validity penalty          |
| Meta-labeling          | Per signal  | Per asset | Position scalar           |
| Macro regime overlay   | Weekly      | Global    | Exposure + SL adjustments |
| Liquidity regime       | Per signal  | Per asset | Exposure + halt logic     |
| PSI drift              | Per cycle   | Per asset | Penalty + halt            |
| Portfolio drawdown     | Global      | Portfolio | Global throttling         |

---

# Failure Isolation

Each `AssetEngine` executes independently via parallel orchestration.

Failures in:

* data ingestion,
* diagnostics,
* governance,
* execution,
* or model inference

cannot halt the global engine.

All assets execute through isolated lifecycle management.

---

# Performance Architecture

QuantForge contains multiple runtime optimizations designed for inference stability and execution throughput.

## Runtime Optimizations

* Vectorized triple-barrier labeling
* Broadcast-based inference operations
* Async diagnostics off hot path
* Daemon consumer threading
* SQLite WAL persistence
* TTL macro cache
* Parallel asset orchestration
* Inference truncation validation
* Object-identity model hot-swap verification

---

# State Architecture

Persistent state is managed through a WAL-mode SQLite store.

## Properties

* O(1) append semantics
* 5-table normalized schema
* replay-oriented persistence
* periodic WAL checkpointing
* deterministic recovery support
* backward-compatible JSON snapshots

---

# Getting Started

```bash
git clone https://github.com/user/quantforge.git
cd quantforge

python -m venv .venv
source .venv/bin/activate

make deps            # pin + install locked dependencies
# or: pip install -r requirements.lock

# Start engine + dashboard
./monitor_all
# or: python main.py
```

Dashboard:

```text
http://localhost:5000
```

---

# Environment Variables

| Variable                      | Required | Purpose                     |
| ----------------------------- | -------- | --------------------------- |
| `PYTHONPATH`                  | Yes      | Set to `.`                  |
| `QUANTFORGE_REFRESH_INTERVAL` | No       | Engine loop interval        |
| `OPENCODE_ZEN_API_KEY`        | No       | Weekly narrative extraction |

---

# Key Scripts

| Script                                 | Purpose                     |
| -------------------------------------- | --------------------------- |
| `scripts/walk_forward_backtest.py`     | Multi-ticker validation     |
| `scripts/score_tickers.py`             | Asset scoring               |
| `scripts/generate_promotion_report.py` | Portfolio report generation |
| `scripts/train_all_assets.py`          | Full retraining             |
| `scripts/generate_snapshot.py`         | Regenerate BASELINE_SNAPSHOT |
| `benchmarks/microbenchmark.py`         | Runtime benchmarking        |

| Make target       | Purpose                     |
| ----------------- | --------------------------- |
| `make deps`       | Pin + install locked deps   |
| `make test`       | Run test suite              |
| `make snapshot`   | Regenerate BASELINE_SNAPSHOT |
| `make lint`       | Compile-check key modules   |

---

# Repository Structure

```text
quantforge/            # Modular core (domain, application, infrastructure)
paper_trading/         # Active paper trading engine and orchestration
features/              # Alpha, archetype, and regime feature engineering
models/                # Model definitions (hybrid ensemble, experts)
labels/                # Triple-barrier and meta-label generation
monitoring/            # PSI drift, validity state, and dashboarding
risk/                  # Drawdown, exposure, and position sizing controls
portfolio/             # Allocation and risk parity logic
backtests/             # Walk-forward and adversarial validation scripts
research/              # Execution surface and shadow cycle investigations
configs/               # Asset and environment YAML configurations
data/                  # Local data storage (raw, processed, research)
scripts/               # Operational and utility scripts
docs/                  # System documentation and ADRs
tests/                 # Comprehensive test suite
requirements.lock      # Pinned dependencies with hashes (commit this)
BASELINE_SNAPSHOT.md   # Auto-generated config snapshot (make snapshot)
LIVE_CONTRACT.md       # Immutable production system contract
```

## Key Components

```text
quantforge/            # New modular core (DDD architecture)
    domain/            # Entities (Asset, Trade), Services (PnL, Volatility)
    application/       # Use cases and ports
    infrastructure/    # Persistence (SQLite), API, Broker adapters

paper_trading/         # Legacy engine (Active)
    engine.py          # Orchestrator
    asset_engine.py    # Per-asset isolation
    state_store.py     # SQLite persistence
    inference/         # Pipeline and training
    execution/         # Policy and entry logic
    governance/        # Risk layers
```

---

# Known Constraints

* Paper trading only
* Yahoo Finance data dependency with automated quality monitoring
* No live brokerage integration
* Ensemble system disabled by default in production (active research)
* Macro data sourced primarily from Yahoo Finance tickers

---

# Roadmap

## Completed (May 2026)

* Dependency pinning (`requirements.lock` with hashes)
* XGBoost native model serialization (`.json`, no pickle)
* SHA-256 checksum verification on cold state snapshots
* Data-quality gate on yfinance pipeline (staleness + NaN detection)
* Auto-generated baselines (`make snapshot`)
* Fix `main.py` entry point dispatcher
* **Architectural Pivot:** Initiated `quantforge/` modular core with DDD principles

## Planned (Q3-Q4 2026)

* Graduate `quantforge/` core to primary engine
* Deterministic full-day replay reconstruction
* Event-sequence validation tooling
* Extended execution quality analytics
* Multi-engine distributed orchestration
* Portfolio-level regime optimization
* Live broker abstraction layer
* Shadow execution comparison tooling

---

# License

MIT License.

Research and paper-trading system only.

Not financial advice.
