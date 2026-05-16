# QuantForge

![Build Status](https://img.shields.io/badge/build-initialized-brightgreen)
![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

QuantForge is a modular multi-asset quantitative research and algorithmic trading framework built for systematic strategy development, machine learning experimentation, portfolio construction, and execution simulation.

The project is designed to support:

- Forex
- Metals
- Equities
- Crypto proxies

and follows an institutional-style research workflow centered around:

- feature engineering
- regime detection
- triple-barrier labeling
- machine learning signal generation
- portfolio optimization
- walk-forward validation
- execution simulation
- live monitoring

---

## Core Philosophy

Markets are non-stationary, noisy, and regime-dependent.

Instead of fitting a single predictive model across all conditions, QuantForge uses a **regime-aware architecture**:

1. Detect market regime
2. Route to specialized strategy/model
3. Generate probabilistic signals
4. Apply risk and portfolio constraints
5. Simulate or execute trades

This architecture avoids one of the most common retail quant mistakes:

> Running the same model across trending, ranging, and high-volatility environments.

---

## Architecture Overview

```text
Data → Features → Labels → Models → Signals → Risk → Portfolio → Backtests → Monitoring → Execution
```

---

## Project Structure

```text
QuantForge/
├── configs/
│   ├── forex.yaml
│   ├── metals.yaml
│   ├── equities.yaml
│   └── crypto.yaml
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── loaders/
│
├── features/
│   ├── base_features.py
│   ├── trend_features.py
│   ├── mean_reversion_features.py
│   ├── volatility_features.py
│   └── cross_asset_features.py
│
├── labels/
│   ├── triple_barrier.py
│   └── meta_labels.py
│
├── models/
│   ├── regime/
│   ├── trend/
│   ├── mean_reversion/
│   ├── volatility/
│   └── ensemble/
│
├── signals/
│   ├── signal_generator.py
│   ├── thresholding.py
│   └── signal_filters.py
│
├── risk/
│   ├── position_sizing.py
│   ├── stop_engine.py
│   ├── exposure_limits.py
│   └── drawdown_controls.py
│
├── portfolio/
│   ├── hrp_allocator.py
│   ├── risk_parity.py
│   └── correlation_clusters.py
│
├── backtests/
│   ├── walk_forward.py
│   ├── execution_simulator.py
│   └── performance_metrics.py
│
├── monitoring/
│   ├── drift_detection.py
│   ├── mlflow_logger.py
│   └── live_dashboard.py
│
├── execution/
│   ├── broker_interface.py
│   ├── order_manager.py
│   └── portfolio_sync.py
│
├── notebooks/
├── tests/
├── main.py
└── requirements.txt
```

---

## Features

### Data Layer
Supports market data ingestion using:

- yfinance
- parquet storage
- incremental updates

Planned:
- Polygon.io
- Alpaca
- Interactive Brokers
- OANDA

Supported assets:

- FX pairs
- metals futures
- ETFs
- crypto proxies

---

### Feature Engineering

Feature families include:

#### Trend Features
- moving average spread
- momentum
- breakout distance
- ADX
- rolling trend strength

#### Mean Reversion Features
- RSI
- Bollinger z-score
- VWAP distance
- rolling percentile rank

#### Volatility Features
- ATR
- realized volatility
- volatility compression/expansion

#### Cross-Asset Features
- SPY risk proxy
- dollar strength proxy
- correlation clusters
- macro context features

---

### Labeling Engine

QuantForge uses **triple-barrier labeling** instead of naive directional labels.

Each sample is labeled using:

- take profit barrier
- stop loss barrier
- timeout barrier

Outputs:

- `1` = take profit hit first
- `-1` = stop loss hit first
- `0` = timeout

This better aligns ML targets with actual trade outcomes.

Optional:
- meta-labeling

---

### Regime Classification

The system first classifies market state into:

- trend
- range
- volatile
- crisis

This acts as a model router.

Example:

```python
if regime == "trend":
    use trend model
elif regime == "range":
    use mean_reversion model
elif regime == "volatile":
    use breakout model
else:
    reduce exposure
```

---

### Models

Initial models:

- XGBoost
- LightGBM
- CatBoost
- Random Forest

Planned:

- LSTM
- Temporal CNN
- Transformer experiments

Ensembling supported via probability aggregation.

---

### Signal Engine

Converts model probabilities into actionable trades.

Example:

```python
long if prob > 0.68
short if prob < 0.32
else flat
```

Signal filters include:

- spread filters
- volatility filters
- news windows
- liquidity filters

---

### Risk Management

Includes:

- volatility targeting
- ATR-based stops
- drawdown governors
- exposure constraints
- portfolio-level risk caps

Example controls:

- max trade risk
- max portfolio exposure
- correlation clustering constraints

---

### Portfolio Allocation

Supported methods:

- Equal weight
- Risk parity
- Hierarchical Risk Parity (HRP)

Portfolio logic accounts for:

- asset correlations
- volatility scaling
- exposure balancing

---

### Backtesting Engine

Supports:

- walk-forward validation
- realistic execution assumptions
- slippage
- spread modeling
- transaction costs

Metrics:

- Sharpe ratio
- Sortino ratio
- CAGR
- max drawdown
- win rate
- profit factor
- turnover

---

### Monitoring

Tracks:

- feature drift
- model drift
- regime drift
- prediction confidence degradation

Includes:

- MLflow experiment logging
- live dashboard support

---

## Installation

Clone repository:

```bash
git clone <repo_url>
cd QuantForge
```

Create environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run:

```bash
python main.py
```

---

## Configuration

Asset behavior is configured using YAML.

Example:

```yaml
symbols:
  - EURUSD=X
  - GBPUSD=X
  - USDJPY=X

timeframe: 1h
risk_per_trade: 0.005
slippage_bps: 1.5
spread_model: variable
rebalance: 1h
```

Each asset class can define:

- symbols
- feature sets
- spread assumptions
- rebalance frequency
- volume reliability

---

## Research Workflow

Recommended development loop:

```text
Hypothesis
→ Feature engineering
→ Label generation
→ Model training
→ Walk-forward backtest
→ Failure analysis
→ Refinement
```

Avoid optimizing for:

- training accuracy
- single backtest equity curves

Optimize for:

- robustness
- stability
- out-of-sample performance

---

## Roadmap

### Phase 1
- [ ] data ingestion pipeline
- [ ] feature engineering base layer
- [ ] triple barrier labeler
- [ ] XGBoost baseline

### Phase 2
- [ ] regime classifier
- [ ] signal thresholds
- [ ] risk engine

### Phase 3
- [ ] walk-forward engine
- [ ] portfolio allocator
- [ ] HRP

### Phase 4
- [ ] paper trading
- [ ] broker integrations

### Phase 5
- [ ] live deployment

---

## Disclaimer

This project is for research, experimentation, and educational purposes.

Nothing here constitutes financial advice or guarantees profitability.

Markets are adversarial, noisy, and regime-changing.

Past performance does not imply future results.

---

## References

Inspired by ideas from:

- Advances in Financial Machine Learning
- Machine Learning for Asset Managers
- systematic trading literature
- institutional quant research workflows

---

## Author

Built by MktOwl.
