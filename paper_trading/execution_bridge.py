"""Connect PaperBroker execution physics to AssetEngine fills.

Phase 5 integration: ExecutionSimulator wraps PaperBroker to add
asymmetric slippage, gap-through modeling, partial fill degradation,
and seeded stochastic latency for stop-loss and take-profit fills.

The simulator sits AFTER PolicyDecision freeze and never mutates it.
"""

from __future__ import annotations

import logging

import numpy as np

from paper_trading.execution.order_manager import OrderManager
from paper_trading.execution.paper_broker import PaperBroker
from paper_trading.execution_simulator import (
    ExecutionSimulator,
    FillResult,
    MarketSnapshot,
)
from paper_trading.decision import PositionIntent
from shared.execution_config import compute_market_impact, compute_slippage_cost

logger = logging.getLogger("quantforge.execution_bridge")


class ExecutionBridge:
    """Simulates realistic fill prices via PaperBroker and ExecutionSimulator.

    Phase 5 (ExecutionSimulator) is an additive degradation layer.
    When enabled, it wraps entry, stop-loss, and take-profit fills
    with realistic market physics. It never improves outcomes.
    """

    def __init__(self, broker: PaperBroker, use_execution_simulator: bool = False, seed: int = 42):
        self.broker = broker
        self.broker.allow_short = True
        self.orders = OrderManager(broker)
        self.simulator = ExecutionSimulator(seed) if use_execution_simulator else None

    def _build_market_snapshot(self, asset: str, mid_price: float) -> MarketSnapshot:
        """Build a MarketSnapshot from broker state."""
        vol_z = self.broker.get_vol_zscore(asset)
        return MarketSnapshot(
            current_price=mid_price,
            open_price=mid_price,
            high_price=mid_price,
            low_price=mid_price,
            vol_zscore=vol_z,
        )

    def estimate_impact_bps(self, asset: str, notional: float) -> float:
        if notional <= 0:
            return 0.0
        config = self.broker._get_config(asset)
        impact = compute_market_impact(notional, config)
        return float(impact * 10000.0)

    def fill_price(
        self,
        asset: str,
        side: str,
        quantity: float,
        mid_price: float,
    ) -> tuple[float, float, float]:
        """
        Returns (fill_price, slippage_bps, impact_bps) using vol-z spread + impact model.

        When ExecutionSimulator is enabled, the entry fill is wrapped
        with seeded noise and degradation. The PolicyDecision is never mutated.
        """
        if mid_price <= 0 or quantity <= 0:
            return mid_price, 0.0, 0.0

        self.broker.set_price(asset, mid_price)
        self.broker._update_vol_tracking(asset, mid_price)
        vol_z = self.broker.get_vol_zscore(asset)
        config = self.broker._get_config(asset)

        # Phase 5: ExecutionSimulator entry fill (degradation only)
        if self.simulator is not None:
            market = self._build_market_snapshot(asset, mid_price)
            result = self.simulator.simulate(
                "entry", side, mid_price, quantity, market, config
            )
            fill = result.fill_price
            slippage_bps = result.slippage_bps
            impact_bps = 0.0
        else:
            slippage = float(compute_slippage_cost(np.array([vol_z]), config)[0])
            impact = float(compute_market_impact(quantity * mid_price, config))
            total = slippage + impact
            fill = mid_price * (1 + total) if side == "buy" else mid_price * (1 - total)
            slippage_bps = (slippage + impact) * 10000.0
            impact_bps = impact * 10000.0

        logger.debug(
            "%s %s fill: mid=%.4f fill=%.4f slip=%.1fbps vol_z=%.2f",
            asset,
            side,
            mid_price,
            fill,
            slippage_bps,
            vol_z,
        )
        return fill, slippage_bps, impact_bps

    def fill_stop_loss(
        self,
        asset: str,
        position: PositionIntent,
        current_price: float,
    ) -> FillResult:
        """Simulate a stop-loss fill with Phase 5 degradation.

        Returns an immutable FillResult. Does not mutate position or policy.
        Falls back to simple price if simulator is disabled.
        """
        if self.simulator is not None:
            config = self.broker._get_config(asset)
            market = self._build_market_snapshot(asset, current_price)
            return self.simulator.simulate_stop_loss(position, current_price, market, config)

        side = "sell" if position.side == "long" else "buy"
        fill_px = position.stop_loss
        return FillResult(fill_px, max(position.vol * 1000, 1.0), 0.0, 0, False, False)

    def fill_take_profit(
        self,
        asset: str,
        position: PositionIntent,
        current_price: float,
    ) -> FillResult:
        """Simulate a take-profit fill with Phase 5 degradation.

        Returns an immutable FillResult. Does not mutate position or policy.
        Falls back to simple price if simulator is disabled.
        """
        if self.simulator is not None:
            config = self.broker._get_config(asset)
            market = self._build_market_snapshot(asset, current_price)
            return self.simulator.simulate_take_profit(position, current_price, market, config)

        side = "sell" if position.side == "long" else "buy"
        fill_px = position.take_profit
        return FillResult(fill_px, max(position.vol * 1000, 1.0), 0.0, 0, False, False)

    def submit_market_order(
        self,
        asset: str,
        side: str,
        quantity: float,
        mid_price: float,
    ) -> tuple[float, str]:
        """Place order through OrderManager; returns (fill_price, order_id)."""
        fill, _, _ = self.fill_price(asset, side, quantity, mid_price)
        order_id = self.orders.submit_market_order(asset, side, quantity, fill_price=fill)
        return fill, order_id or ""
