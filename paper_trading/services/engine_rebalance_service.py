import logging
from datetime import datetime

import pandas as pd
import pytz

from paper_trading.governance.multipliers import compute_effective_multipliers
from paper_trading.ops.data_fetcher import fetch_history
from shared.sizing import compute_equal_risk_weights

logger = logging.getLogger("quantforge.engine_rebalance_service")

ET = pytz.timezone("US/Eastern")


class EngineRebalanceService:
    def __init__(self, engine):
        self.engine = engine

    def should_rebalance(self) -> bool:
        engine = self.engine
        today = datetime.now(tz=ET).date()
        today_dow = today.weekday()
        if today_dow != engine._rebalance_dow:
            return False
        if engine._rebalance_last_day == today:
            return False
        engine._rebalance_last_day = today
        return True

    def _collect_daily_returns(self, window: int = 252) -> pd.DataFrame:
        engine = self.engine
        price_data: dict[str, pd.Series] = {}
        for name, asset in engine.assets.items():
            px = asset.current_price
            if px is None or px <= 0:
                continue
            try:
                hist = fetch_history(asset.ticker, period=f"{window + 60}d", interval="1d")
                if hist is not None and "close" in hist.columns and len(hist) >= window:
                    price_data[name] = hist["close"]
            except Exception:
                continue
        if not price_data:
            return pd.DataFrame()
        df = pd.DataFrame(price_data)
        returns = df.pct_change().dropna()
        return returns.iloc[-window:] if len(returns) > window else returns

    def detect_crisis_regime(self) -> bool:
        for name, asset in self.engine.assets.items():
            state = getattr(asset.validity_sm, "current_state", None)
            if state is not None and "CRISIS" in str(state).upper():
                return True
        return False

    def rebalance_portfolio(self) -> None:
        engine = self.engine
        window = 252
        returns = self._collect_daily_returns(window)
        if returns.empty or len(returns.columns) < 2:
            logger.info("Risk parity skipped — insufficient price data")
            return

        total_value = engine._state.compute_mtm_total()

        adjusted = returns.copy()
        for col in adjusted.columns:
            if col not in engine.assets:
                continue
            asset = engine.assets[col]
            _, _, combined_size = compute_effective_multipliers(
                base_sl=asset.sl_mult,
                base_tp=asset.tp_mult,
                validity_state=asset.validity_sm.current_state.value if asset.validity_sm else "YELLOW",
                regime_geometry=asset.regime_geometry,
                narrative_sl_mult=asset.governance._narrative_sl_mult,
                liquidity_sl_mult=asset.governance._liquidity_sl_mult,
                narrative_size_scalar=asset.governance._narrative_size_scalar,
                liquidity_size_scalar=asset.governance._liquidity_size_scalar,
            )
            vol_scale = 1.0 / combined_size if combined_size > 0 else 1.0
            adjusted[col] = adjusted[col] * vol_scale

        try:
            weights = compute_equal_risk_weights(adjusted)
        except Exception as e:
            logger.error("Risk parity optimization failed: %s", e)
            return

        if not weights:
            return

        total_w = sum(weights.get(n, 0.0) for n in engine.assets)
        if total_w <= 0:
            return

        engine._rebalance_weights = {n: weights.get(n, 0.0) / total_w for n in engine.assets}

        for name, asset in engine.assets.items():
            target = total_value * engine._rebalance_weights[name]
            asset.set_capital_base(target)

        logger.info(
            "Risk parity rebalanced %d assets — weights: %s",
            len(engine.assets),
            {n: f"{w:.3f}" for n, w in engine._rebalance_weights.items()},
        )
