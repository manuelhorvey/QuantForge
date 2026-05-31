# QuantForge — Risk & Governance Layer

Nine independent governance mechanisms operating at different frequencies and granularities.

| Layer | Frequency | Scope | Effect |
|---|---|---|---|
| Validity state machine | Per tick | Per asset | Exposure 0–100% |
| Feature stability | Per retrain | Per asset | Validity penalty |
| Meta-labeling (XGBoost) | Per signal | Per asset | Continuous size scalar [0–1] |
| 5D drift monitoring | Per tick | Per asset | Alert |
| Shadow risk engine | Per tick | Per asset | Advisory |
| Macro narrative | Weekly | Global | SL width, position size |
| Liquidity regime | Per signal | Per asset | SL width, size, halt |
| PSI drift | Per cycle | Per asset | Validity penalty, halt at 3+ SEVERE |
| Regime conviction flip gate | Per flip | Per asset | Blocks signal flips when regime is decisive but model is uncertain |

## 1. Validity State Machine

Each asset runs an independent validity state machine in `monitoring/validity_state_machine.py`:

- **GREEN** → full exposure (1.0×)
- **YELLOW** → reduced exposure (0.5×)
- **RED** → halted (0.0× — no PnL accrual)

Transitions use **hysteresis bands**, **exponential inertia smoothing**, and a **regime persistence lock** to prevent rapid state flipping. Input signals:

- Drawdown vs threshold
- Monthly profit factor
- Signal drought (days since last signal)
- Confidence drift from expected baseline

**Exposure gating**: Each tick, `run_once()` calls `update_validity()` and sets `pos_mgr.exposure_multiplier` to the state machine's output. This directly scales all PnL calculations — GREEN=full, YELLOW=half, RED=flat.

## 2. Feature Importance Stability

Training-window feature importances are persisted per asset per retrain cycle. Two metrics feed into the ValidityStateMachine:

- **Jaccard similarity** (top-10 features): < 0.6 → −0.10 penalty, < 0.4 → −0.25 penalty
- **Spearman rank correlation** (shared features): < 0.7 → −0.08 penalty, < 0.5 → −0.20 penalty
- **Worst-wins aggregation**: the most negative penalty is applied (not averaged)

## 3. Meta-Labeling Layer (XGBoost)

A secondary confidence filter applied after the primary XGBoost signal:

- **Model**: XGBoost XGBClassifier (`labels/meta_labels.py:MetaLabelModel`)
- **Features** (7): primary model probabilities, regime state, periods in state, stability penalty, close price, archetype, market structure
- **Decision**: continuous probability — below `threshold` (0.55 for most assets) → zero notional; above → `_meta_size_multiplier()` maps [threshold, 1.0] → [min_size, 1.0] linearly
- **Integration**: `_last_meta_proba` fed into `_composite_size_scalar()` alongside governance scalars; meta-confidence is size-only — never modifies TP geometry, trailing, or scale-out schedules

**Historical note:** An earlier LogisticRegression implementation (`shared/meta_labeling.py`) was removed after AUC 0.49-0.55 validation (effectively random). The XGBoost replacement uses richer features and continuous sizing to avoid the hard ENTER/BLOCK switching that made the old approach fragile.

## 4. 5D Drift Monitoring

- Model drift (KL divergence)
- Signal flip rate
- PnL MAE
- Feature set Jaccard similarity
- Regime consistency score

## 5. Shadow Risk Engine

- `risk_governance.py` — Real-time risk evaluation (composite risk score, exposure multiplier)
- `shadow_actions.py` — Corrective action recommendations (PAUSE / REDUCE / MONITOR)
- Advisory layer — computed but not enforced (validity state machine is the enforcement layer)

## 6. Macro Narrative Governance (Weekly)

Weekly LLM-driven macro context overlay that adjusts execution parameters based on FXStreet analysis:

- **Pipeline**: FXStreet "Week ahead" article → Claude API (structured JSON extraction) → `MacroNarrativeFeatures` → governance scalars
- **Regime output**: `risk_off`, `geopol_tension`, `risk_on`, `data_driven` — derived from geopol risk score, fed/central bank hawkishness, currency biases
- **Governance rules** (via `narrative_governance_scalars()`):
  - `geopol_risk_score > 0.7` → SL widens by `geopol_sl_widen_pct` (default +10%)
  - `overall_regime == "risk_off"` → position size reduces by `risk_off_size_reduce_pct` (default -20%)
  - `confidence < min_confidence` (default 0.6) or stale narrative → no governance applied
- **Human review step**: Narrative lands as `narrative_pending.json`; must be confirmed via dashboard **NARR PENDING** button or auto-confirms at Monday noon (`auto_confirm_deadline_hour: 12`)
- **Staleness**: ≥7 days since week_start → stale flag suppresses governance, shown as `(STALE)` on dashboard
- **Failure mode**: scrape/LLM error → narrative carries forward with `fetch_error` status; dashboard shows yellow **NARR ERR** badge
- **Integration**: `_narrative_sl_mult` multiplied into SL in `_open_position`; `_narrative_size_scalar` applied in `_sizing_config` and execution bridge notional; `narrative_ok` flag in `check_halt_conditions` with -0.10 validity penalty
- **State storage**: `data/live/narrative_active.json`, `narrative_pending.json`
- **Config**: `configs/paper_trading.yaml` → `narrative_config` section
- **Requires**: `OPENCODE_ZEN_API_KEY` env var

## 7. Liquidity Regime Model (Per-Tick)

Real-time liquidity proxy computed from daily OHLCV on every signal cycle:

- **Features** (`compute_liquidity_features()`):
  - **Volume z-score**: rolling 21d z-score of volume (negative = thin)
  - **Amihud illiquidity ratio z-score**: `|return| / (volume × close)`, normalized (positive = illiquid)
  - **Corwin-Schultz spread estimate**: bid-ask spread proxy from daily high/low
- **Regime output**: `NORMAL` / `THIN` / `STRESSED` — threshold-driven from config params
- **Governance rules** (via `liquidity_governance_scalars()`):
  - `THIN` → SL widens by `thin_sl_widen_pct` (+15%), size reduces by `thin_size_reduce_pct` (-15%)
  - `STRESSED` → SL widens by `stressed_sl_widen_pct` (+30%), size reduces by `stressed_size_reduce_pct` (-30%), sets halted flag
- **Integration**: `_liquidity_sl_mult` multiplied into SL in `_open_position`; `_liquidity_size_scalar` applied in sizing and execution notional; `liquidity_ok` flag in `check_halt_conditions` (STRESSED halts) with -0.10 validity penalty
- **Dashboard**: LIQ THIN (yellow) / LIQ STRSD (red) badge in header with per-asset hover tooltip
- **Config**: `configs/paper_trading.yaml` → `liquidity_config` section with threshold and pct params

## 8. PSI Drift Monitoring (Per-Cycle)

Automated distribution shift detection per feature per asset:

- **Core** (`monitoring/psi_monitor.py`):
  - `compute_psi()` — fixed-width bins from baseline min/max, first/last bin extended to ±inf for overflow
  - `classify_drift(psi)` — NO_DRIFT (< 0.1), MODERATE (0.1 – 0.2), SEVERE (> 0.2)
  - `PSIDriftEntry` dataclass per feature with `psi`, `classification`, `trend` (STABLE / INCREASING / DECREASING vs previous cycle), `importance_score`
  - `PSISnapshot` dataclass per asset with per-feature list, worst_classification, moderate_count, severe_count, psi_ok, penalty
- **Baseline**: Training window feature distribution persisted to `data/live/psi_baseline/{asset}.parquet` immediately after `model.fit()` — only updated on retrain
- **Current window**: Rolling 21-day inference feature distribution, computed each cycle from `features_df.tail(21)`
- **Feature scoping**: Only top-10 most important features per asset (from `importance_store`)
- **Governance rules**:
  - Any MODERATE feature → −0.08 validity penalty
  - Any SEVERE feature → −0.20 validity penalty (penalties additive: max −0.28 combined)
  - 3+ SEVERE features → `psi_ok = False`, hard halt on asset
  - Trend arrow (↑↓→) on dashboard distinguishes data glitch (single SEVERE, STABLE trend) from genuine drift (SEVERE + INCREASING)
- **Penalty accumulation**: PSI penalty is additive with feature stability penalty (both are separate terms in `update_validity()`) — worst-wins at each penalty type, summed across types
- **Dashboard**: `PSIDriftCard.tsx` — per-asset table with color-coded feature rows, trend arrows, classification badges, worst-classification summary, collapsible halted section
- **Endpoint**: `GET /psi.json` (30s cache)

## 9. Regime Conviction Flip Gate (Per-Flip)

A pre-close gate that suppresses signal flips when the market structure has clearly shifted but the model is lagging — deferring to the regime signal.

- **Core** (`paper_trading/governance/conviction_gate.py`):
  - `RegimeRow` TypedDict stores per-bar regime probabilities
  - `evaluate_regime_conviction_gate()` — AND-gate with five exit paths
- **AND condition**: only allow flip when ALL of:
  - `regime_margin = abs(P_trend - P_range) ≥ threshold`
  - `model_confidence ≤ confidence_threshold` (model is uncertain)
  - `bars_in_current_regime ≥ min_bars_in_regime` (regime is stable)
- **Pass-through paths** (flip allowed without AND check):
  - `volatile_bypass` — structural shock override (`P_volatile == 1.0`) is unambiguous
  - `model_aligned` — model is already confident in the flip direction
  - `no_regime_data` — classifier hasn't run yet (cold start)
- **Placement**: evaluated in `asset_engine.py:387-392` **before** position close — if the gate blocks, the position stays open and no flip cooldown is set, avoiding the flat-limbo edge case
- **Integration**: cooldown (`min_flip_interval_bars: 3`) and conviction gate are independent filters at different points: cooldown blocks re-entry after an executed flip; conviction gate prevents the flip from executing at all
- **Calibration**: threshold (`regime_margin_threshold: 0.35`) empirically derived from 394 flip events across 9 dashboard assets (`oos_predictions.parquet`). Surviving flips at 0.35 show 53.6% win rate and 1.43 profit factor; blocked flips show 45.9% WR and 0.87 PF (noise correctly filtered)
- **Regime bias in calibration sample**: 62.8% trend, 33.8% range, 3.3% volatile — in a ranging market the gate will block more aggressively, which is correct behavior
- **Config**: `configs/paper_trading.yaml` → `optimizations.regime_conviction_flip_gate` (enabled by default)
- **Monitoring**: each blocked flip logs `"flip blocked by conviction gate — <reason>"` — grep for the reason distribution after a few days

## Multiplicative Governance Chain

The SL layers stack multiplicatively on the existing SL chain:

```
final_sl_mult = base_sl_mult × regime_geom_sl × narrative_sl_mult × liquidity_sl_mult
final_size_scalar = min(narrative_size_scalar × liquidity_size_scalar, 0.30)
```

Validity penalties (feature stability + PSI drift) are additive and feed into the validity state machine, NOT into the SL/size chain:

```
validity_score = 0.80 − drawdown_penalty − pf_penalty − drought_penalty − drift_penalty − narrative_penalty − liquidity_penalty + stability_penalty + psi_penalty
```

Each layer is independently configurable, independently gated (by confidence, staleness, or threshold), and independently observable in the dashboard.
