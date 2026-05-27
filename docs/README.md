# QuantForge Documentation

Project documentation and reference materials for the QuantForge quantitative trading framework.

## Quick Start

| Guide | Description |
|-------|-------------|
| [`PAPER_TRADING_RUNBOOK.md`](PAPER_TRADING_RUNBOOK.md) | Daily/weekly ops, halt responses, troubleshooting |
| [`SYSTEM_OVERVIEW.md`](SYSTEM_OVERVIEW.md) | Architecture, components, data flow (includes Phases 0–6 execution pipeline) |
| [`GOVERNANCE_LAYER.md`](GOVERNANCE_LAYER.md) | 7-layer governance: validity, narrative, liquidity, PSI, halt chain |
| [`FEATURES.md`](FEATURES.md) | FeatureContract system, driver atlas, cross-asset isolation, archetype classification |
| [`ARCHITECTURE_FOUNDATIONS.md`](ARCHITECTURE_FOUNDATIONS.md) | Model architecture, labeling, regime classifier, execution pipeline decomposition |
| [`HARDENING_ROADMAP.md`](HARDENING_ROADMAP.md) | Execution physics, extended history, lead-lag, adaptive macro, Phases 0–6 |
| [`SURVIVAL_SIMULATION.md`](SURVIVAL_SIMULATION.md) | Adversarial survival testing, deleveraging feedback |

### Execution Research Framework (Phases 0–6) ✅ Complete

| Phase | Layer | Module |
|-------|-------|--------|
| 0 | Frozen Kernel + Labels | `labels/triple_barrier.py` |
| 1 | Entry Quality Engine | `paper_trading/entry_optimizer.py`, `paper_trading/deferred_entry.py` |
| 2 | TP/Exit Geometry | `paper_trading/tp_compiler.py`, `paper_trading/scale_out.py` |
| 3 | Archetype Classification | `features/archetypes.py` |
| 4 | Execution Policy Layer | `paper_trading/execution_policy.py` — also: `_can_enter()` single entry gate in `asset_engine.py` |
| 5 | Fill Realism Layer | `paper_trading/execution_simulator.py`, `slippage_model.py`, `fill_model.py`, `latency_model.py` |
| 6 | Trade Attribution | `paper_trading/trade_attribution.py` — persists to parquet via `state_store.py` |

### Derived Metrics Engine ✅

| Module | File | Purpose |
|--------|------|---------|
| EIS | `shared/metrics/eis.py` | Execution Impact Score (slippage × fill × latency) |
| FQI | `shared/metrics/fqi.py` | Fill Quality Index (ratio × gap × partial × latency) |
| MAE/MFE | `shared/metrics/mae_mfe.py` | Time/ATR-normalized adverse/favorable excursion |
| Shadow Divergence | `shared/metrics/shadow.py` | Live vs shadow R delta + exit-reason divergence |
| Attribution Waterfall | `shared/metrics/attribution.py` | 4-domain PnL decomposition + domain quality scores |

### Dashboard (6 Execution Layers)

| Layer | Component | Purpose |
|-------|-----------|---------|
| 0 | `FilterBar` | Persistent archetype/regime/asset chips |
| 1 | `ExecutionQualityStrip` | EIS/FQI per-asset KPI row |
| 2 | `AttributionBreakdownCard` + `PnLWaterfall` | Domain scores + PnL decomposition |
| 3 | `MaeMfeScatter` | MAE vs MFE colored by archetype |
| 4 | `SlippageHistogram` + `FillQualityGauge` | Friction distribution + fill quality indicator |
| 5 | `TradeExecutionTable` + `TradeDetailPanel` | Full attribution field drill-down |
| 6 | `ShadowComparisonTable` + `ShadowDivergenceChart` | Shadow vs live exit reason/R analysis |

## ADRs

Architecture Decision Records in [`adr/`](adr/) — see [`adr/ADR-000-index.md`](adr/ADR-000-index.md) for the full list.

## Conventions

- ADRs follow the standard [Michael Nygard template](https://github.com/joelparkerhenderson/architecture-decision-record)
- All docs are written in Markdown
- `LIVE_CONTRACT.md` at the project root is the immutable system contract
