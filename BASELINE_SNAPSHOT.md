# BASELINE SNAPSHOT — AUTO-GENERATED

Generated: 2026-06-10
Source: `configs/paper_trading.yaml`, `LIVE_CONTRACT.md`

---

## 1. SYSTEM CONFIG

| Parameter | Value |
|---|---|
| Capital | $100,000 |
| Position size | 0.95 |
| Retrain freq | annual |
| Retrain window | 5y |
| Drawdown limit | -0.15 |
| Data source | MT5 (yfinance fallback) |
| Ensemble | per-asset (60/40 when regime model exists) |

---

## 2. ASSET ALLOCATION

| Asset | Ticker | Allocation | sl_mult | tp_mult | max_depth |
|---|---|---|---|---|---|
| GC | GC=F | 7.0% | 1.00 | 4.00 | 2 |
| USDCHF | USDCHF=X | 4.0% | 0.85 | 3.00 | 4 |
| AUDCHF | AUDCHF=X | 5.0% | 2.75 | 3.50 | 3 |
| USDCAD | USDCAD=X | 5.0% | 2.50 | 2.03 | 5 |
| ES | ES=F | 7.0% | 2.00 | 5.50 | 2 |
| NQ | NQ=F | 7.0% | 2.50 | 5.00 | 2 |
| GBPCAD | GBPCAD=X | 5.0% | 2.50 | 2.50 | 2 |
| GBPNZD | GBPNZD=X | 5.0% | 3.00 | 1.00 | 3 |
| NZDCAD | NZDCAD=X | 5.0% | 2.50 | 4.00 | 2 |
| ^DJI | ^DJI | 4.0% | 0.50 | 4.00 | 4 |
| EURUSD | EURUSD=X | 4.0% | 3.00 | 1.50 | 4 |
| NZDUSD | NZDUSD=X | 5.0% | 2.50 | 1.50 | 5 |
| GBPAUD | GBPAUD=X | 5.0% | 1.00 | 2.00 | 3 |
| NZDCHF | NZDCHF=X | 7.0% | 1.00 | 4.00 | 2 |
| CADCHF | CADCHF=X | 5.0% | 1.00 | 4.00 | 2 |
| AUDUSD | AUDUSD=X | 4.0% | 1.50 | 4.00 | 2 |
| AUDNZD | AUDNZD=X | 3.0% | 2.00 | 1.00 | 3 |
| EURCHF | EURCHF=X | 5.0% | 1.00 | 3.00 | 4 |
| EURCAD | EURCAD=X | 2.0% | 1.00 | 1.00 | 3 |
| EURNZD | EURNZD=X | 3.0% | 1.50 | 2.50 | 3 |
| GBPCHF | GBPCHF=X | 3.0% | 1.00 | 2.00 | 2 |

---

## 3. MODEL FILES

**Directory:** `paper_trading/models/` — 21 `.json` models

- `GC_model.json`
- `USDCHF_model.json`
- `AUDCHF_model.json`
- `USDCAD_model.json`
- `ES_model.json`
- `NQ_model.json`
- `GBPCAD_model.json`
- `GBPNZD_model.json`
- `NZDCAD_model.json`
- `DJI_model.json`
- `EURUSD_model.json`
- `NZDUSD_model.json`
- `GBPAUD_model.json`
- `NZDCHF_model.json`
- `CADCHF_model.json`
- `AUDUSD_model.json`
- `AUDNZD_model.json`
- `EURCHF_model.json`
- `EURCAD_model.json`
- `EURNZD_model.json`
- `GBPCHF_model.json`

---

## 4. EXECUTION GOVERNANCE

| Layer | State |
|---|---|
| Narrative | enabled |
| Liquidity | enabled |
| Regime geometry | per-asset (GREEN, YELLOW, RED) |
| Flip gate | enabled |
| Meta-labeling | enabled |
| PSI drift | enabled |
| Portfolio drawdown | enabled |

---

## 5. OPTIMIZATIONS

| Optimization | Value |
|---|---|
| Truncate inference | auto |
| Batch HTTP | True |
| SQLite state | True |
| Vectorized labels | True |
| Async diagnostics | True |
| Regime conviction flip gate | enabled |

---

## 6. LIVE_CONTRACT.md REFERENCE

For full contract details see [`LIVE_CONTRACT.md`](LIVE_CONTRACT.md).

Key invariants from the contract:
- XGBoost binary classifier with `.json` serialization
- Daily OHLCV from MT5 / yfinance
- Triple-barrier labeling with per-asset pt_sl
- Fixed-threshold signal strategy at 0.45
- 21 promoted assets with risk-parity weights
- Per-asset max_depth (2–5)
- Dynamic SL/TP with trailing stops and per-asset min_rr_ratio

---

*This file documents the baseline system state at the time of generation. Update via `make snapshot`.*
