# QuantForge — System Overview

High-level architecture, component responsibilities, and data flow for the QuantForge quantitative trading framework.

---

## Architecture Diagram

```mermaid
graph TD
    subgraph Data_Layer [Raw Data Layer]
        A1[yfinance: OHLCV daily]
        A2[FRED: macro rate_diff, yield_curve]
        A1 & A2 --> B[Data Integration]
    end

    subgraph Feature_Layer [Feature Layer]
        B --> C[base_features.py]
        B --> D[regime_features.py]
        B --> E[structural_features.py]
        B --> F[interaction_features.py]
        B --> G[macro features]
    end

    subgraph Model_Layer [Model Layer]
        C & D & E & F & G --> H[HybridRegimeEnsemble]
        H --> H1[Global backbone]
        H --> H2[Regime experts]
        H --> H3[Macro expert]
    end

    subgraph Regime_Layer [Regime Layer]
        D --> I[RegimeClassifier]
        I --> I1[KER + ADX + vol]
        I1 --> I2{TREND/RANGE/VOLATILE/NEUTRAL}
    end

    subgraph Signal_Layer [Signal Layer]
        H --> J[RegimeAwareSignalGen]
        I2 --> J
        J --> J1[Threshold 0.45]
        J --> J2[Confidence = max P]
    end

    subgraph Archetype_Layer [Archetype Classification — Phase 3]
        J1 & J2 --> A1[SetupArchetype: 5 pure-feature types]
        A1 --> A2[BREAKOUT / TREND_PULLBACK]
        A1 --> A3[MEAN_REVERSION / VOL_EXPANSION / MOMENTUM_IGNITION]
    end

    subgraph Entry_Layer [Entry Quality — Phase 1]
        A2 & A3 --> E1[EntryOptimizer]
        E1 --> E2{ENTER / DEFER / SKIP}
        E2 -->|DEFER| E3[DeferredEntry: idempotent entry_id]
    end

    subgraph Policy_Layer [Execution Policy — Phase 4]
        E2 --> P1[ExecutionPolicyLayer: POLICY_MAP]
        P1 --> P2[PolicyDecision: immutable instruction packet]
        E3 -->|Triggered| P1
    end

    subgraph Fill_Layer [Fill Realism — Phase 5]
        P2 --> F1[ExecutionSimulator]
        F1 --> F2[SlippageModel: asymmetric SL/TP]
        F1 --> F3[FillModel: gap-through / partial fill]
        F1 --> F4[LatencyModel: seeded delay]
        F2 & F3 & F4 --> F5[FillResult: frozen]
    end

    subgraph Attribution_Layer [Trade Attribution — Phase 6]
        F5 --> T1[AttributionCollector: observe-only]
        T1 --> T2[4-domain: Prediction / Execution / Exit / Friction]
    end

    subgraph Monitoring_Layer [Monitoring Layer]
        T1 --> K[Validity State Machine]
        K --> K1[GREEN 1.0 / YELLOW 0.5 / RED 0.0]
        K --> K2[Hysteresis + temporal smoothing]
    end

    subgraph Execution_Layer [Paper Trading Engine]
        K1 --> L[AssetEngine x8 + BTC satellite]
        L --> L1[8 core assets + BTC satellite bucket]
        L1 --> L2[Live inference every 5 min]
        L2 --> L3[Vol-scaled sizing + SL/TP + scale-out]
        L3 --> L4[PnL tracking: state.json + trade_journal.parquet]
    end

    subgraph Metrics_Layer [Derived Metrics Engine]
        T1 --> M1[shared/metrics/ — EIS, FQI, MAE/MFE normalization]
        M1 --> M2[shadow divergence, attribution waterfall, domain scores]
        M2 --> M3[Analytics Snapshot — frequency-gated aggregation]
    end

    subgraph UI_Layer [Web Dashboard]
        L4 & M3 --> D[stdlib http.server REST API]
        D --> D1[Portfolio: state.json, trades.json, equity_history.json]
        D --> D2[Execution: execution-quality, slippage, fill-quality]
        D --> D3[Attribution: trades, summary, waterfall]
        D --> D4[Shadow: trades, divergence summary]
        D --> D5[Governance: narrative, liquidity, PSI, risk-parity]
    end
```

---

## Component Responsibilities

### Data Layer (`data/`)

| Component | File | Responsibility |
|-----------|------|---------------|
| Downloader | `data/loaders/downloader.py` | Daily OHLCV via yfinance |
| Macro Loader | `data/loaders/macro_loader.py` | FRED data — rate_diff, yields, DXY, VIX |
| Weekly Pipeline | `data/weekly_pipeline.py` | Weekly resample (W-FRI), full feature pipeline |
| Live State | `data/live/` | Runtime engine state: state.json, history.parquet |

### Feature Engineering (`features/`)

Features are computed independently per module and concatenated by common index. Each module returns a DataFrame that can be included or excluded per asset.

| Module | Key Features | Used By |
|--------|-------------|---------|
| base | EMA spreads, ADX, MACD, RSI, Bollinger Z-score | All models |
| regime | Hurst exponent, KER, ADX, vol_zscore, compression | Regime classifier |
| structural | Price slope, curvature, path efficiency, skew, kurtosis | Research only |
| interaction | Regime contrast, entropy, transition risk | Research only |
| macro (loader) | rate_diff, dxy_mom, yield_slope, yield_delta | Macro expert head |
| archetypes | Breakout detection, trend pullback, mean reversion, vol expansion, momentum ignition | EntryOptimizer, policy dispatch |

### Model Layer (`quantforge/`, `shared/model.py`)

**Standard XGBoost** per asset (`shared/model.py:StandardModel`)
- `xgboost.XGBClassifier` with `n_estimators=300, max_depth=2, learning_rate=0.02`
- 3-class softprob: BUY / HOLD / SELL
- Optional macro expert head (`HybridEnsemble`) with adaptive blend weight
- Training via `shared/strategies/` abstract base classes
- Walk-forward validated per asset (5yr train / 1yr test / 1yr step, bootstrap gate p<0.10)

**RegimeClassifier** (`models/regime/regime_classifier.py`)
- TREND score: KER × 1.3 × 0.45 + (ADX / 45) × 0.55
- RANGE score: (1 - KER × 1.8) × 0.35 + (1 - ADX / 30) × 0.35 + (1 - compression) × 2.0 × 0.3
- VOLATILE gate: vol_zscore > 1.35 OR compression > 1.45 (overwrites probabilistic)
- NEUTRAL: softmax confidence < 0.45
- Smoothing: 10-bar rolling mode with persistence lock

### Risk & Monitoring (`risk/`, `monitoring/`)

**ValidityStateMachine** (`monitoring/validity_state_machine.py`)
- Input: validity score (composite of model confidence, feature drift, market conditions)
- Output: state (GREEN/YELLOW/RED) with capital allocation (1.0/0.5/0.0)
- Hysteresis bands: GREEN entry 0.70, exit 0.60; YELLOW entry 0.45, exit 0.40; RED entry 0.40, exit 0.50
- Exponential decay smoothing (α=0.7, β=0.3)
- Regime persistence lock (minimum 5 periods before transition allowed)
- Capital allocation is stepped, not continuous — makes state auditable

**Position Sizing** (`shared/sizing.py:VolTargetSizing`)
- Base dollar risk × regime multiplier
- Engine adds volatility scalar via `VolTargetSizing`
- ATR-based barrier geometry via `shared/volatility.py:VolatilityPrimitive` — primary vol source for labels, SL/TP, shadow replay, and attribution

### Archetype Classification (`features/`)

| Component | File | Responsibility |
|-----------|------|---------------|
| SetupArchetype | `features/archetypes.py` | 5 pure-feature archetypes: MOMENTUM_IGNITION, MEAN_REVERSION, BREAKOUT_TEST, TREND_PULLBACK, VOLATILITY_EXPANSION |
| ArchetypeClassifier | `features/archetypes.py` | Computes archetype from feature vector without model inference |

### Entry Quality (`paper_trading/`)

| Component | File | Responsibility |
|-----------|------|---------------|
| EntryOptimizer | `paper_trading/entry_optimizer.py` | Maps (archetype, MarketStructureState) → EntryAction (ENTER / DEFER / SKIP) |
| DeferredEntry | `paper_trading/deferred_entry.py` | Idempotent entry_id from hash(signal_snapshot + symbol + timestamp_bucket); PENDING/TRIGGERED/EXPIRED/CANCELLED state machine; persists across ticks |
| EntryAction | `paper_trading/decision.py` | Routing enum: ENTER (immediate), DEFER (conditional trigger), SKIP (abstain) |

### Execution Policy (`paper_trading/`)

| Component | File | Responsibility |
|-----------|------|---------------|
| BasePolicy | `paper_trading/execution_policy.py` | Abstract base; archetypePolicy mixin; POLICY_MAP dispatch |
| PolicyDecision | `paper_trading/decision.py` | Frozen dataclass — immutable instruction packet with archetype, action, TPGeometry, market_state hash |
| TPGeometry | `paper_trading/decision.py` | Frozen dataclass — tp_mult, sl_mult, scale_out_tiers, vol_adjustment |

### TP Compiler (`paper_trading/`)

| Component | File | Responsibility |
|-----------|------|---------------|
| TPCompiler | `paper_trading/tp_compiler.py` | regime×archetype TP geometry; backloaded scale-out tiers per archetype; vol-expansion adjustment; inverted regime TP multipliers |

### Fill Realism (`paper_trading/`)

| Component | File | Responsibility |
|-----------|------|---------------|
| ExecutionSimulator | `paper_trading/execution_simulator.py` | Orchestrator: simulate(), simulate_entry(), simulate_stop_loss(), simulate_take_profit(); all randomness seeded and deterministic |
| SlippageModel | `paper_trading/slippage_model.py` | Asymmetric slippage: SL 1.5× base + seeded noise (adverse); TP 0.1× base (neutral/near-zero) |
| FillModel | `paper_trading/fill_model.py` | Gap-through detection (fills at gap-open if price gaps through stop); partial fill degradation (min_fill_prob 0.60) |
| LatencyModel | `paper_trading/latency_model.py` | Seeded bar-level execution delay (0–3 bars, gamma-distributed) |
| FillResult | `paper_trading/decision.py` | Frozen dataclass — fill_price, fill_qty, slippage_bps, gap_through, partial, latency_bars |

### Trade Attribution (`paper_trading/`)

| Component | File | Responsibility |
|-----------|------|---------------|
| AttributionCollector | `paper_trading/trade_attribution.py` | Observe-only collector; wired into AssetEngine open/close lifecycle; 4-domain causal split |
| PredictionAttribution | `paper_trading/trade_attribution.py` | Directional correctness, confidence calibration, regime alignment at entry |
| ExecutionAttribution | `paper_trading/trade_attribution.py` | Entry timing quality, slippage impact, fill efficiency, counterfactuals |
| ExitAttribution | `paper_trading/trade_attribution.py` | MAE/MFE time-normalized, exit reason decomposition, scale-out efficiency |
| FrictionAttribution | `paper_trading/trade_attribution.py` | Spread cost, market impact, latency cost, total friction |
| CounterfactualMetric | `paper_trading/trade_attribution.py` | What-if: perfect entry, zero slippage, ideal exit vs actual |

### Execution (`paper_trading/`)

**AssetEngine** (per-asset instance)
- Loads serialized model pickle
- Fetches live data (yfinance)
- Runs inference → signal → confidence
- Routes through archetype classifier → EntryOptimizer → ExecutionPolicyLayer → ExecutionSimulator → AttributionCollector
- `_can_enter()`: **single entry authority gate** — enforces hard same-bar stop-out lock, cooldown penalty, pending-entry conflict check. All entry sources (model decisions via `_apply_decision()`, deferred entries via `_poll_pending_entries()`) route through this gate
- `_apply_decision()`: dispatches PolicyDecision to state mutation (gated by `_can_enter()`)
- `_poll_pending_entries()`: checks DeferredEntry triggers each cycle (gated by `_can_enter()`)
- `_cooldown_penalty()`: decaying entry threshold penalty (4h half-life) after stop-out
- Manages position: entry, SL/TP, PnL tracking
- Attribution: wired into open/close lifecycle — `AttributionCollector` records prediction, execution, exit, and friction data per trade; flushed to parquet at close
- Updates live state (history.parquet, state.json)

**PaperTradingEngine** (orchestrator)
- Manages 8 AssetEngine instances + BTC satellite
- Label architectures: tb20 (triple-barrier) for FX/equities, fwd60 (60-day forward return) for GC
- 7-layer governance: validity state machine, meta-labeling (XGBoost confidence filter), macro narrative, liquidity regime, PSI drift, drawdown, signal drought
- SL/TP chain: `final_sl = base × regime_geom × narrative_sl × liquidity_sl`
- Scale-out: 4-tier profit-taking for 6 of 8 core assets (AUDJPY, CHFJPY, EURAUD, EURCAD, GBPCAD, USDJPY)
- Dynamic SL/TP calibration at startup (ATR-based, calibration_scale=1.2)
- Runs every 300s (configurable via `QUANTFORGE_REFRESH_INTERVAL` env var)
- Exposes state via JSON for dashboard, persists to Parquet/JSON

**HTTP Server** (`paper_trading/serve.py`, `serve_routes.py`)
- Zero-dependency stdlib `http.server`-based REST API with `serve_routes.py` route registry
- In-memory TTL cache per endpoint (5-30s), gzip compression for large responses
- Analytics snapshot cache with frequency gating (recomputes every 5 requests)

**Portfolio & Engine Endpoints:**
- `/state.json` — full engine snapshot (5s cache)
- `/trades.json?limit=N&offset=M` — paginated trade journal (5s cache)
- `/equity_history.json` — equity curve (30s cache)
- `/confidence.json` — confidence history (5s cache)
- `/volatility.json` — volatility metrics (5s cache)
- `/risk.json`, `/risk/{asset}.json` — risk metrics (5s cache)
- `/trade-outcomes.json` — TP/SL/win rates per asset (5s cache)
- `/logs` — engine log tail (no cache)

**Governance Endpoints:**
- `/governance.json` — governance state (5s cache)
- `/risk-parity.json` — allocation weights (5s cache)
- `/narrative.json` — macro narrative (5s cache)
- `/liquidity.json` — liquidity regime (30s cache)
- `/psi.json` — PSI drift per feature (30s cache)
- `/health.json`, `/health/{asset}.json` — per-asset health scores (5s cache)
- `/shadow-actions.json`, `/shadow-actions/{asset}.json` — shadow action recommendations (5s cache)

**Execution & Attribution Endpoints:**
- `/attribution/trades.json?limit=N&offset=M&archetype=&regime=&asset=` — attribution records with filtering (5s cache)
- `/attribution/summary.json` — domain scores + archetype/regime stratification (5s cache)
- `/attribution/waterfall.json` — 4-domain PnL decomposition (5s cache)
- `/execution/quality.json` — EIS/FQI per-asset (5s cache)
- `/execution/slippage.json` — entry/exit slippage distribution (5s cache)
- `/execution/fill-quality.json` — fill quality gauge data (5s cache)

**Shadow & Analytics Endpoints:**
- `/shadow/trades.json?limit=N&alt_label=` — shadow trade records (5s cache)
- `/shadow/summary.json` — shadow divergence overall + by label (30s cache)
- `/analytics/snapshot.json` — aggregated analytics: overall stats, by-archetype/by-regime breakdowns, shadow summary (30s cache, frequency-gated)

**Health:**
- `/ping` — health check (no cache)
- `POST /narrative/confirm` — confirm weekly narrative
- `POST /weekly-review/acknowledge` — acknowledge weekly review

**Dashboard** (`paper_trading/dashboard/` — React + Vite + Tailwind + react-query, 70+ components)
- **7-section anchor nav**: Portfolio, Signals, Execution, Trades, Governance, Risk, Charts — scroll-aware via `IntersectionObserver`
- **6-layer Execution section**:
  - Layer 0: `FilterBar` — persistent archetype/regime/asset filter chips
  - Layer 1: `ExecutionQualityStrip` — EIS/FQI per-asset KPI row
  - Layer 2: `AttributionBreakdownCard` + `PnLWaterfall` — domain scores grid + Recharts PnL decomposition
  - Layer 3: `MaeMfeScatter` — MAE vs MFE scatter colored by archetype
  - Layer 4: `SlippageHistogram` + `FillQualityGauge` — entry/exit slippage distribution + SVG fill quality indicator
  - Layer 5: `TradeExecutionTable` + `TradeDetailPanel` — full attribution field table with row-click drill-down (domain scores per trade)
  - Layer 6: `ShadowComparisonTable` + `ShadowDivergenceChart` — shadow vs live exit reason/R divergence + KPI summary
- **9 TanStack Query hooks** for execution/attribution/shadow data with 30-60s polling
- Full dark/light theme with localStorage persistence
- TradeFeed with pagination, SignalsTable with asset name search, sortable columns
- GovernanceStateCards with halted status, validity state badges, animated RED pulse
- Scale-out tier visualization per asset (filled vs pending blocks)
- PSI Drift panel with feature-level distribution shift, trend arrows, color-coded badges
- RiskParityPanel with governance-colored allocation bars
- AlertFeed with governance halt/state-change/PSI-SEVERE events, dismissible
- ConnectionStatus bar monitoring 5 endpoints (Live/Degraded/Offline)
- Satellite card showing entry/SL/TP prices, exit reason history
- Zod schema validation on all API responses
- SessionStorage-persisted sort state and alert history

### Validation (`backtests/`)

**WalkForwardValidator**
- Expanding window (all data up to year N-1)
- Default: 5yr train / 1yr test / 1yr step
- Bootstrap p < 0.10 deployment gate (10,000 permutations)
- Metrics: PF, Sharpe, win rate, expectancy, max DD, CAGR
- 4/6 windows must pass gate for asset deployment

### Derived Metrics Engine (`shared/metrics/`)

| Module | Functions | Purpose |
|--------|-----------|---------|
| `eis.py` | `compute_eis`, `compute_eis_from_df` | Execution Impact Score — weighted composite: slippage (40%), fill quality (35%), latency (25%) |
| `fqi.py` | `compute_fqi`, `compute_fqi_from_df` | Fill Quality Index — `fill_qty_ratio × gap_penalty × partial_penalty × latency_penalty` |
| `mae_mfe.py` | `normalize_mae_mfe`, `compute_mae_mfe_stats` | Time-normalized adverse/favorable excursion; ATR-normalized for cross-asset comparison |
| `shadow.py` | `compute_shadow_divergence`, `compute_r_delta_distribution` | Live vs shadow R delta distribution; exit-reason divergence rate |
| `attribution.py` | `compute_waterfall`, `compute_domain_scores` | 4-domain PnL decomposition waterfall; per-trade prediction/execution/exit/friction scores |

All modules are **deterministic and stateless** — no runtime engine dependency. Consumed by `serve_routes.py` for dashboard API responses.

### Data Persistence (`state_store.py`)

| Method | Storage | Purpose |
|--------|---------|---------|
| `save_snapshot` / `load_snapshot` | `state.json` | Atomic engine state with TTL cache |
| `append_trade` / `read_trades` | `trade_journal.parquet` | Trade journal with exit reasons |
| `append_attribution` / `read_attribution` | `attribution.parquet` | 4-domain attribution records with filtering |
| `append_shadow_trade` / `read_shadow_trades` | `shadow_trades.parquet` | Shadow counterfactual trade outcomes |
| `write_trade_outcomes_cache` | `trade_outcomes.json` | Aggregated TP/SL/win rates per asset |
| `write_analytics_snapshot` | `analytics_snapshot.json` | Frequency-gated derived metrics aggregation |
| `save_equity_history` / `read_equity_history` | `equity_history.parquet` | Equity curve over time |

### Configuration (`configs/`)

YAML configs define per-asset parameters:
- Asset ticker, allocation weight, features
- Halt conditions (drawdown limits per asset)
- Retrain frequency (annual)
- Volatility scaling toggle
- Per-asset model parameters (overrides defaults)

---

## Data Flow

### Research Pipeline

```mermaid
graph TD
    R1[OHLCV daily] --> R2[weekly_pipeline.py]
    R3[Macro FRED] --> R2
    R2 --> R4[Feature engineering]
    R4 --> R5[Labeling]
    R5 --> R6[Walk-forward validation]
    R6 --> R7[Bootstrap gate]
    R7 --> R8[Model serialization]
    R8 --> R9[Paper trading ready]
```

### Paper Trading Pipeline

```mermaid
graph TD
    T1[yfinance 5 min] --> T2[Feature computation live]
    T3[Load model pickle] --> T4[Inference XGBoost]
    T2 & T4 --> T5[Signal + Confidence > 0.45?]
    T5 --> T6[Archetype Classification: Phase 3]
    T6 --> T7[EntryOptimizer: Phase 1]
    T7 --> T8{EntryAction}
    T8 -->|ENTER| T9[ExecutionPolicy: Phase 4]
    T8 -->|DEFER| T10[DeferredEntry: monitor trigger]
    T8 -->|SKIP| T17[Skip Signal]
    T17 --> T18[Dashboard + telemetry]
    T10 -->|Triggered| T9
    T9 --> T9a{_can_enter() Gate}
    T9a -->|BLOCKED| T17
    T9a -->|PASS| T11
    T11 --> T12[Governance layer: 7 conditions]
    T12 --> T13[Validity state machine check]
    T13 --> T14[Position management: entry/SL/TP/scale-out]
    T14 --> T15[TradeAttribution: Phase 6]
    T15 --> T16[Persist: attribution + shadow trades + journal to parquet]
    T16 --> M1[Derived Metrics: EIS, FQI, MAE/MFE, divergence]
    M1 --> M2[Analytics Snapshot: frequency-gated aggregation]
    M2 --> T18[Dashboard + telemetry]
```

---

## Key Entry Points

| Action | Command/File |
|--------|-------------|
| Run walk-forward research | `python equity/walk_forward_xlf.py` |
| Start paper trading + dashboard | `./monitor_all` (rebuilds frontend, starts engine + HTTP server) |
| Wipe state & restart fresh | `rm -rf data/live/ && ./monitor_all` |
| Dashboard URL | `http://127.0.0.1:5000` |
| Run tests | `make test` |
| Run full test suite with coverage | `make test-cov` |
| CI pipeline | `.github/workflows/ci.yml` |
| Daily data refresh | `data/weekly_pipeline.py` |

---

## Configuration Reference

**`configs/paper_trading.yaml`:**
- `capital: 100000` — Starting capital
- `position_size: 0.95` — Max position fraction
- Per-asset: ticker, weight, features, drawdown limits, halt conditions
- `retrain_freq: annual` — Model retraining frequency
- Per-asset ATR params: `atr_period`, `atr_mult_sl`, `atr_mult_tp` — Dynamic barrier geometry via `shared/volatility.py:VolatilityPrimitive`

**Environment:**
- `PYTHONPATH=.:$PYTHONPATH` — Required for module imports
- `.venv/` — Python virtual environment
- `paper_trading/models/*.pkl` — Serialized models
