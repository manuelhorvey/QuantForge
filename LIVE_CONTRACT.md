# LIVE SYSTEM CONTRACT — IMMUTABLE SOURCE OF TRUTH

This file defines the exact behavior of the production paper trading system.
Any deviation from this contract is a trading bug.
Changes require full regression validation.

## 1. MODEL CONTRACT

**Type:** `xgboost.XGBClassifier`
**Objective:** `binary:logistic`
**Architecture:** Binary classifier (HOLD dropped, {-1, 1} mapped to {0, 1})
**Constructor:**
```
n_estimators=300, max_depth=2, learning_rate=0.02,
random_state=42, n_jobs=1, tree_method='hist', verbosity=0
```
**Signature:** `model.predict(X: pd.DataFrame) -> np.ndarray`
**Output shape:** `(N, 1)` — raw probability of LONG class
**Pipeline expansion:** Raw output is expanded to 3-column proba `[p_short, 0, p_long]` in
`paper_trading/inference/pipeline.py:_generate_and_apply()`
**Serialization:** `model.save_model(path)` / `model.load_model(path)` — `.json` format
**Path:** `paper_trading/models/{asset_name}_model.json`

---

## 2. SIGNAL THRESHOLD CONTRACT

**Strategy:** `FixedThresholdStrategy` (`shared/signal.py`)
**Threshold:** `0.45` (float, default param of `generate_signal()`)

| Condition | Signal | Label |
|---|---|---|
| `proba[:,2] > 0.45` AND `proba[:,0] <= 0.45` | BUY | 2 |
| `proba[:,0] > 0.45` AND `proba[:,2] <= 0.45` | SELL | 0 |
| BOTH `> 0.45` | BUY (long wins — order-dependent) | 2 |
| NEITHER `> 0.45` | FLAT | 1 |

**Confidence:** `confidence = max(proba[:,2], proba[:,0])`
**Confidence output:** `round(confidence * 100, 2)` (percent, 0-100 scale)

---

## 3. FEATURE CONTRACT

**Primary builder:** `features/alpha_features.py:build_alpha_features()`
**Input:** `prices` (close series), `rate_diffs` (simulated), `dxy`, `vix`, `spx`, `commodities`
**Data ingestion:** `features/data_fetch.py:fetch_asset_data(ticker)` — 10y yfinance

### Per-asset alpha features

| Category | Features | Derived from |
|---|---|---|
| Vol-adjusted carry | `{asset}_carry_vol_adj` | Close returns × vol normalization |
| Multi-horizon momentum | `{asset}_mom_21d`, `_63d`, `_126d`, `_252d` | Close pct_change over windows |
| Z-score reversion | `{asset}_zscore_20` | 20-day rolling z-score of close |
| Vol regime ratio | `{asset}_vol_ratio` | Short-term / long-term vol |
| Day-of-week signal | `{asset}_dow_signal` | Calendar day-of-week encoding |
| DXY momentum | `dxy_mom_21`, `dxy_mom_63` | DXY index pct_change |
| VIX momentum | `vix_mom_21`, `vix_mom_63` | VIX pct_change |
| SPX momentum | `spx_mom_21`, `spx_mom_63` | SPX pct_change |
| Commodity momentum | `wti_mom_21`, `wti_mom_63` | WTI crude pct_change |

### Archetype features (inference-only, from full-history OHLCV)

Computed inline in `paper_trading/inference/pipeline.py:_generate_and_apply()` via `ta` library:

| Feature | Formula | Window |
|---|---|---|
| `ema_spread` | (EMA20 − EMA50) / EMA50 | 20/50 |
| `adx` | ADX(high, low, close) | 14 |
| `rsi` | RSI(close) | 14 |
| `bb_zscore` | (close − BB_mavg) / (BB_std / 2) | 20 |

---

## 4. DATA CONTRACT

### Sources
| Source | Data | Frequency |
|---|---|---|
| `yfinance` | Daily OHLCV for all assets + macro (DXY=DX-Y.NYB, VIX=^VIX, SPX=^GSPC, WTI=CL=F, TNX=^TNX) | Daily bars |
| FRED | Not used in production pipeline | — |

### Ingestion rules
- `fetch_live(ticker)` — 500 days, truncated to 250d for XGBoost (TZ-aware → normalized to UTC date via `pipeline.py:51-56`)
- `fetch_asset_data(name, ticker)` — 10y close + macro (TZ-naive date index)
- `fetch_asset_ohlcv(ticker)` — 10y full OHLCV (TZ-naive date index, 0.5s rate-limited)
- All date indices are `datetime64[ns]` at daily resolution (no intraday)
- No FRED data — all macro derived from yfinance tickers

### Index normalization
All yfinance downloads produce TZ-naive DatetimeIndex at daily resolution.
The pipeline normalizes `fetch_live()` output by converting to UTC before stripping TZ:
```python
df.index = pd.to_datetime(df.index.tz_convert("UTC").date)
```

---

## 5. LABEL CONTRACT

**Label function:** `features/labels.py:triple_barrier_labels()`
**Input parameters** (per-asset, from `configs/paper_trading.yaml`):
- `pt_sl`: `(tp_mult, sl_mult)` — barrier multiples of ATR
- `vertical_barrier`: 10 bars

**Label pipeline:**
1. Triple-barrier touch → {-1 (SELL), 0 (HOLD), 1 (BUY)}
2. Binary reduction: drop HOLD (0), map {-1, 1} → {0, 1}
3. Binary XGBoost trains on {0, 1} labels only

**Default `pt_sl` by asset:**
| Most assets | BTCUSD |
|---|---|
| (1.5, 2.0) | (2.5, 3.0) |

---

## 6. MODEL TRAINING CONTRACT

**Pipeline:** `paper_trading/inference/training.py:AssetTrainingPipeline.train()`
**Data window:** 10y history from yfinance, train on last `retrain_window` years (default 5)
**Minimum samples:** 100 binary labels; 2+ unique classes
**Train/val split:** 80/20 chronological, stratified by label if minimum class count ≥ 2
**Post-training:**
- Persist PSI baseline from training feature distribution
- Train optional meta-label model (XGBoost)
- Log feature importances + stability (Jaccard + Spearman)
- Train optional regime-conditional model + configure ensemble

---

## 7. INFERENCE PIPELINE CONTRACT

**Pipeline:** `paper_trading/inference/pipeline.py:AssetInferencePipeline._generate_and_apply()`
**Per-cycle (every 300s / 5 min):**

1. `fetch_live(ticker)` — 250 days OHLCV
2. Normalize index to UTC TZ-naive
3. `refresh_price()` — patch last close with real-time or 5d fallback
4. `ffill()` close column
5. `fetch_asset_data()` — 10y close + macro
6. `build_alpha_features()` — produce alpha_df with ~30 feature columns
7. `fetch_asset_ohlcv()` — 10y full OHLCV for archetype features
8. Compute archetype features (ema_spread, adx, rsi, bb_zscore)
9. PSI drift check (rolling 21d vs baseline; skipped on first cycle)
10. XGBoost predict → 3-column proba expansion
11. Optional regime ensemble blend (if regime model + ensemble configured)
12. Optional meta-label inference
13. `FixedThresholdStrategy.compute()` → signal + decision
14. Archetype classification → `TradeDecision`
15. `_apply_decision()` → policy routing → entry/position management

---

## 8. PORTFOLIO CONTRACT

**Builder:** `paper_trading/portfolio_builder.py:build_paper_portfolio()`
**Source:** `configs/paper_trading.yaml`

### Current assets (15 promoted)
| Asset | Ticker | Allocation | sl_mult | tp_mult |
|---|---|---|---|---|
| BTCUSD | BTC-USD | 6.5% | 3.0 | 2.5 |
| EURGBP | EURGBP=X | 6.5% | 2.0 | 1.5 |
| GC | GC=F | 6.5% | 2.0 | 1.5 |
| NZDCHF | NZDCHF=X | 6.5% | 2.0 | 1.5 |
| CHFJPY | CHFJPY=X | 6.5% | 2.0 | 1.5 |
| CADJPY | CADJPY=X | 6.5% | 2.0 | 1.5 |
| USDCHF | USDCHF=X | 6.5% | 2.0 | 1.5 |
| EURJPY | EURJPY=X | 6.5% | 2.0 | 1.5 |
| EURCAD | EURCAD=X | 6.5% | 2.0 | 1.5 |
| AUDCHF | AUDCHF=X | 6.5% | 2.0 | 1.5 |
| USDJPY | USDJPY=X | 6.5% | 2.0 | 1.5 |
| USDCAD | USDCAD=X | 6.5% | 2.0 | 1.5 |
| GBPCHF | GBPCHF=X | 6.5% | 2.0 | 1.5 |
| ES | ES=F | 7.7% | 2.0 | 2.5 |
| NQ | NQ=F | 7.8% | 2.0 | 2.5 |

### BTC satellite
- 5% AUM cap, vol target 40%, drawdown limit 25%
- Macro gate (VIX, DXY, vol z-score, portfolio returns, crisis regime)
- Managed by `paper_trading/satellite/engine.py:HighVolSatellite`

---

## 9. POSITION SIZING CONTRACT

**Strategy:** Equal-risk weights via `shared/sizing.py:compute_equal_risk_weights()`
**Capital utilization cap:** `configs/paper_trading.yaml:position_size` (default 0.95)
**Per-asset allocation:** Determined by `PaperBroker` from `execution_configs`
**Size scalar chain:**
```
final_size = base × governance_scalar × meta_confidence_scalar
```
- Governance scalar: validity state machine (GREEN=1.0, YELLOW=0.5, RED=0.0)
- Meta-confidence scalar: `_meta_size_multiplier()` maps [threshold, 1.0] → [min_size, 1.0]

---

## 10. ASSET SCREENING & PROMOTION CONTRACT

**Screening pipeline:**
1. `scripts/walk_forward_backtest.py --tickers` — 3y window, 1y step, 5 folds, per-asset pt_sl
2. `scripts/score_tickers.py` — composite score (IC + hit rate + consistency + bidirectionality)
3. `scripts/generate_promotion_report.py` — classification (GREEN/YELLOW/RED) + YAML config block

**Promotion criteria:**
| Condition | Threshold |
|---|---|
| IC | > 0.03 |
| Hit rate | > 0.40 |
| FLAT rate | < 70% |
| Positive fold rate | ≥ 50% |
| Long signal rate | > 5% |
| Short signal rate | > 5% |

**Output:** `walkforward/promotion_report.json`, `walkforward/PROMOTION_REPORT.md`

---

## 11. GOVERNANCE CONTRACT

Seven layered governance mechanisms, each independently configurable:

| Layer | Frequency | Effect | Config key |
|---|---|---|---|
| Validity state machine | Per tick | Exposure 0–100% | `halt.*` |
| Feature stability | Per retrain | Validity penalty | — |
| Meta-labeling (XGBoost) | Per signal | Size scalar [0–1] | `meta_labeling` |
| Macro narrative | Weekly | SL +10%, size −20% | `narrative_config` |
| Liquidity regime | Per signal | SL +15/30%, size −15/30%, halt | `liquidity_config` |
| PSI drift | Per cycle | Validity penalty, halt at 3+ SEVERE | — |
| Portfolio drawdown | Per cycle | Circuit breaker at −15% | `portfolio_drawdown_limit` |

See `docs/GOVERNANCE_LAYER.md` for full detail.

---

## 12. SYSTEM INVARIANTS

1. No train/serve skew — same alpha feature builder in training and inference
2. No look-ahead — labels computed from future data only in training, never in inference
3. TZ-naive date alignment — all pipeline indices normalized to UTC date
4. Per-asset model independence — each asset has its own XGBoost binary model
5. Strict signal/execution separation — model produces probabilities only; execution resolved by policy layer
6. Worst-wins penalty aggregation — most negative governance penalty applied, not averaged
7. Frozen execution contract — PolicyDecision → FillResult → AttributionRecord is immutable causal chain
8. Single entry authority — `_can_enter()` is the sole gate for all entry sources
9. Binary signal — model trains on {-1, 1} labels only; HOLD dropped
10. Walk-forward validated — every promoted asset passes 3yr expanding window backtest

---

## 13. DISCLAIMER

Paper trading system only. No live capital execution. Not financial advice.
Past walk-forward performance is not indicative of future results.
