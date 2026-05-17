# QuantForge

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![Status](https://img.shields.io/badge/status-research-yellow)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

QuantForge is a modular quantitative research framework for regime-conditioned equity and FX strategy research. The current implementation focuses on XLF (financial sector ETF) with a macro+price 4-feature model, following a year-long EURUSD research phase that established the macro-signal architecture.

This is a research system, not a production trading bot. The current stack is designed to answer three questions:

- Does macro signal (rate differentials, yield curve) transfer from FX to equities?
- Can a minimal 4-feature model produce stable out-of-sample returns on sector ETFs?
- When is the macro-price relationship stable enough to allocate risk?

---

## Current Architecture (Equity Track)

```text
Raw OHLCV (XLF, SPY)
  -> Triple barrier labels (pt_sl=2, vb=20)
  -> Macro features (rate_diff, 2y_yield_delta_63)
  -> Price features (mom_63, vs_spy_63)
  -> XGBoost multiclass classifier (300 trees, depth 2)
  -> Bootstrap-verified expectancy
```

The current design is intentionally minimal — the EURUSD phase proved that complexity amplifies noise faster than signal:

- **Macro features describe the environment, not the price response.** `yield_slope` and `real_yield_10y` were removed after diagnostic showed they dominated the model with environment-level bias that didn't translate to tradeable direction.
- **Price momentum captures what the market is doing.** `mom_63` and `vs_spy_63` provide discriminative power that macro alone cannot.
- **Rate expectations (2y_yield_delta_63) bridge the two.** The 63-day change in 2-year yields captures forward-looking rate expectations that separate the 2022 bear from the 2023-2024 rally.

### EURUSD Phase — Key Lessons (2016-2026 Daily)

The first year of research established critical architecture that transferred to equities:

| Finding | Impact |
|---------|--------|
| Macro-only XGBoost on EURUSD: P(short)=0.61, max conf=0.85 | Proved macro signal exists at daily frequency |
| Price features (25+) drown out macro signal in XGBoost tree splits | Led to MacroExpertHead with protected 0.45 blend weight |
| yield_slope and real_yield_10y are high-info about environment, low-info about price | Removed from equity model |
| Every layer beyond macro-only degraded results | Minimal viable system — 4 features, one model |
| Rolling window regime shifts killed walk-forward performance | 5-year windows needed for regime diversity |

### Equity Phase — Current Diagnostic Status

**XLF walk-forward (5-year train, 1-year test, 1-year step)**:

```
Year    PF      Exp          L/S       Edge (bootstrap)
2018    0.92    -0.000388    235/16    -
2019    1.07    +0.000229    175/77    -
2020    1.03    +0.000304    253/0     -
2021    1.29    +0.001179    211/24    -
2022    0.98    -0.000150    197/54    noise (p=0.571)
2023    1.23    +0.000801    91/159    borderline (p=0.111)
2024    1.34    +0.000978    125/127   SIGNAL (p=0.047)
```

**Net annual returns after 0.01% trade cost**:

```
Year    XLF net     QQQ net     Combined
2019    +3.25%      -2.85%      +0.20%
2020    +5.12%      -17.09%     -5.98%
2021    +25.14%     +24.90%     +25.02%
2022    -6.25%      -24.97%     -15.61%
2023    +17.24%     +27.62%     +22.43%
2024    +21.95%     +17.69%     +19.82%
AVG     +11.08%     +4.22%      +7.65%
```

**Current state**: 5/6 years positive on XLF. 2022 loss (-6.25%) is a known structural issue: 2017-2021 training window is 80% bull market, and momentum features chase into the bear. QQQ amplifies the 2022 loss and reduces combined average. Best risk-adjusted path is 100% XLF.

---

## Project Structure

```text
QuantForge/
|-- __init__.py
|-- main.py
|-- requirements.txt
|-- .gitignore
|
|-- backtests/
|   |-- rolling_retrain.py           # Rolling retrain (EURUSD daily/weekly)
|   |-- rolling_retrain_weekly.py     # Weekly retrain
|   |-- walk_forward.py               # EURUSD walk-forward
|
|-- configs/
|   |-- forex.yaml
|   |-- equities.yaml                 # Placeholder
|   |-- crypto.yaml                   # Placeholder
|
|-- data/
|   |-- loaders/
|   |   |-- downloader.py
|   |   |-- macro_loader.py           # FRED macro factors
|   |-- raw/                          # yfinance OHLCV parquets
|   |   |-- EURUSD_1d.parquet
|   |   |-- GBPUSD_1d.parquet
|   |   |-- SPY_1d.parquet
|   |-- processed/
|       |-- macro_factors.parquet
|       |-- macro_features.parquet
|       |-- *features*.parquet        # EURUSD weekly/daily features
|       |-- *label*.parquet
|
|-- diagnostics/                      # EURUSD diagnostics
|   |-- threshold_sweep.py
|   |-- regime_ablation.py
|   |-- phase3_validation.py
|   |-- model_validity_timeline.py
|   |-- ...                           # 10+ additional diagnostics
|
|-- equity/                           # Equity track (active)
|   |-- __init__.py
|   |-- diagnostic_xlf_macro.py       # Macro-only isolation test
|   |-- walk_forward_xlf.py           # XLF walk-forward with bootstrap
|   |-- walk_forward_qqq.py           # QQQ walk-forward
|
|-- features/
|   |-- base_features.py
|   |-- regime_features.py
|   |-- structural_features.py
|   |-- interaction_features.py
|   |-- ...                           # Placeholders
|
|-- labels/
|   |-- triple_barrier.py             # Triple barrier labeling
|
|-- models/
|   |-- hybrid_ensemble.py            # HybridRegimeEnsemble (XGBoost)
|   |-- macro_expert_head.py          # Macro-protected expert head
|   |-- regime/regime_classifier.py
|   |-- ensemble/model_router.py
|
|-- signals/
|   |-- signal_generator.py
|
|-- monitoring/
|   |-- validity_state_machine.py
|   |-- drift_detection.py
|
|-- risk/
|   |-- position_sizing.py
|-- tests/
```

---

## Feature Stack

### Equity Track (Active)

Implemented in `equity/`:

```python
XLF_FEATURES = [
    'rate_diff',           # Fed-ECB divergence (level context)
    '2y_yield_delta_63',   # Rate expectation direction
    'xlf_mom_63',          # 63-day price momentum
    'xlf_vs_spy_63',       # 63-day relative strength vs SPY
]
```

Four features. No regime classifier, no hybrid ensemble, no state machine. The EURUSD phase proved that protected macro signal + minimal feature set outperforms complex architecture on out-of-sample data.

Removed features:
- `yield_slope` — high-info about environment, low-info about price direction
- `real_yield_10y` — same, and remained near bearish extremes through 2023-2024 rallies
- All 25+ price-derived features from EURUSD phase — drowned out macro signal

### Macro Features (FRED Data)

Loaded from `data/processed/macro_factors.parquet` (FRED series via pandas-datareader, no API key required):

- `fed_funds` / `ecb_rate` → `rate_diff`
- `us_2y` / `us_10y` → `yield_slope`, `2y_yield_delta_63`
- `dxy` → `dxy_mom_21`, `dxy_mom_63`
- `DFII10` → `real_yield_10y`

Features are computed daily from FRED weekly/daily releases, forward-filled to asset calendar.

---

## Backtesting

### XLF Walk-Forward (Active)

```bash
export PYTHONPATH=$PYTHONPATH:. && python equity/walk_forward_xlf.py
```

5-year train / 1-year test / 1-year step. Four features. XGBoost (300 trees, depth 2, lr 0.02). Bootstrap p-value on PF for 2022-2024 windows. Output:

```text
Year    Exp          PF     Sharpe   L/S      p(PF<1.0)
2022    -0.000150    0.98   -0.15    197/54   0.571 noise
2023    +0.000801    1.23    1.24    91/159   0.111 borderline
2024    +0.000978    1.34    1.73    125/127  0.047 SIGNAL
```

### QQQ Walk-Forward

```bash
export PYTHONPATH=$PYTHONPATH:. && python equity/walk_forward_qqq.py
```

Identical config, asset = QQQ. Used for cross-asset comparison.

### XLF Macro-Only Diagnostic

```bash
export PYTHONPATH=$PYTHONPATH:. && python equity/diagnostic_xlf_macro.py
```

Reproduces the isolation test: macro features only (no momentum). Confirms macro-only ceiling on equities — P(short)=0.60 but 94% short bias.

### EURUSD Walk-Forward (Historical)

```bash
export PYTHONPATH=$PYTHONPATH:. && python backtests/walk_forward.py
```

Historic reference. EURUSD with hybrid ensemble + MacroExpertHead. Not actively maintained.

---

## Running the Research Pipeline

Recommended workflow for equity track:

```bash
# 1. Set up environment
export PYTHONPATH=$PYTHONPATH:.

# 2. Run macro-only isolation test (confirm signal exists)
python equity/diagnostic_xlf_macro.py

# 3. Run walk-forward (full 4-feature model)
python equity/walk_forward_xlf.py
```

---

## Key Research Findings

### EURUSD Phase (2016-2026 Daily)

1. **Macro signal is real**: DXY momentum and rate differentials predict FX direction correctly. Macro-only XGBoost produced P(short)=0.6083, max conf=0.7034 on 2022-2024.
2. **Price features drown out macro signal**: 25+ price features in joint training pushed P(short) to 0.3456 (4:1 long bias, directionally wrong).
3. **Protected macro head fixes this**: MacroExpertHead at 0.45 fixed blend weight restored correct directional bias (P(short)=0.45).
4. **Signal is weekly-frequency**: Macro features operate at weekly scale. Converting to weekly bars (Path 1) confirmed the signal but training window collapsed (18 months = only 78 weekly rows).
5. **yield_slope and real_yield_10y are environment features, not price features**: Removing them from the equity model improved results more than any architecture change.

### Equity Phase (XLF, Daily)

1. **Macro-only ceiling on equities**: Macro features alone produce P(short)=0.60 but 94% short bias — they capture environment, not price response.
2. **Price momentum + rate expectations = discriminative power**: Adding mom_63, vs_spy_63, 2y_yield_delta_63 flips 2023 signal from short to long.
3. **5-year training windows are necessary**: 3-year windows regime-chase. 5-year windows contain enough regime diversity (bull, COVID, bear, recovery).
4. **2022 loss is structural, not random**: 2017-2021 training window is 80% bull market. No feature addition fixes a training distribution problem.
5. **Bootstrap test validates 2024 edge**: p(PF<1.0)=0.047 — statistically significant at 95% confidence.
6. **FILTERS DON'T HELP**: Hiking cycle filter on top of macro-featured model made 2022 worse (PF 0.90 → 0.86). The model already has the macro features; layering another macro rule adds friction not signal.

### Active Research Questions

- Does the XLF 4-feature model generalize to other sector ETFs (XLE, XLI)?
- Can XLF + an uncorrelated strategy (e.g., trend-following on bonds) improve the 2022 window?
- How does live slippage compare to the 0.01% per-trade cost assumption?

---

## Configuration

Asset universe and trading parameters are defined in `configs/`:

```yaml
# forex.yaml (historical)
symbols:
  - EURUSD=X
  - GBPUSD=X
  - USDJPY=X
  - GC=F
```

Equity track is configured in `equity/` scripts directly — no YAML needed for a 4-feature model.

---

## Installation

```bash
git clone <repo_url>
cd QuantForge
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export PYTHONPATH=$PYTHONPATH:.
```

Basic smoke test:

```bash
Python version >= 3.10
```

---

## Current Research State

What is working:

- XLF 4-feature walk-forward: 5/6 years positive, 11.08% avg net return
- 2024 bootstrapped edge: statistically significant (p=0.047)
- 2023: near-significant (p=0.111) with 1.23 PF
- Macro-only diagnostic cleanly reproduces on XLF
- Feature environment/price distinction is understood and applied
- Minimal viable system validated (4 features > 25+ features + ensemble)
- EURUSD architecture (regime classifier, hybrid ensemble, macro head) available for cross-reference

Current bottlenecks:

- 2022 structural loss (-6.25%) from bull-market training distribution
- QQQ adds correlated 2022 failure and reduces combined average
- No live trading track record
- XLE, XLI, and other sector ETFs not yet tested
- No portfolio-level risk management beyond single-asset sizing
- EURUSD diagnostics not maintained in parallel

Near-term research direction:

- Paper trade XLF with 6-month minimum observation period
- Test XLF model on XLE (energy, DXY-driven) for potential portfolio diversification
- Monitor live walk-forward alignment with backtest distribution
- Add slippage and spread cost tracking from live data

---

## Disclaimer

This project is for research, experimentation, and education.

Nothing here is financial advice or a guarantee of profitability. Markets are noisy, adversarial, and non-stationary. Past performance does not imply future results.

---

## Author

Built by MktOwl.
