"""Connect PaperBroker execution physics to AssetEngine fills."""

from __future__ import annotations

import logging

import numpy as np

from paper_trading.execution.order_manager import OrderManager
from paper_trading.execution.paper_broker import PaperBroker
from shared.execution_config import compute_market_impact, compute_slippage_cost

logger = logging.getLogger("quantforge.execution_bridge")


class ExecutionBridge:
    """Simulates realistic fill prices via PaperBroker without owning portfolio state."""

    def __init__(self, broker: PaperBroker):
        self.broker = broker
        self.broker.allow_short = True
        self.orders = OrderManager(broker)

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
        """
        if mid_price <= 0 or quantity <= 0:
            return mid_price, 0.0, 0.0

        self.broker.set_price(asset, mid_price)
        self.broker._update_vol_tracking(asset, mid_price)
        vol_z = self.broker.get_vol_zscore(asset)
        config = self.broker._get_config(asset)

        slippage = float(compute_slippage_cost(np.array([vol_z]), config)[0])
        impact = float(compute_market_impact(quantity * mid_price, config))
        total = slippage + impact

        fill = mid_price * (1 + total) if side == "buy" else mid_price * (1 - total)

        logger.debug(
            "%s %s fill: mid=%.4f fill=%.4f slip=%.1fbps impact=%.1fbps vol_z=%.2f",
            asset,
            side,
            mid_price,
            fill,
            slippage * 10000,
            impact * 10000,
            vol_z,
        )
        return fill, slippage * 10000.0, impact * 10000.0

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
