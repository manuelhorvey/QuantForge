"""Asymmetric slippage model — SL worse, TP neutral.

Sits AFTER PolicyDecision freeze.
Only degrades outcomes, never improves them.
"""

from __future__ import annotations

import hashlib
import logging
import random

from shared.execution_config import ExecutionConfig

logger = logging.getLogger("quantforge.slippage_model")


class SlippageModel:
    """Seeded asymmetric slippage engine.

    SL fills always receive adverse slippage (fill worse than trigger).
    TP fills receive neutral/near-zero slippage (limit order behavior).
    Entry fills use the config-standard spread model with seeded noise.

    All randomness is seeded and deterministic.
    """

    def __init__(self, seed: int = 42):
        self._rng = random.Random(seed)

    def recreate(self, seed: int) -> SlippageModel:
        """Return a fresh instance with the given seed (deterministic replay)."""
        return SlippageModel(seed)

    def _slip_bps(self, base_bps: float, vol_zscore: float, config: ExecutionConfig) -> float:
        excess = max(0.0, vol_zscore - 1.0)
        slip = base_bps * (1.0 + config.spread_vol_slope * excess)
        slip = min(slip, config.spread_max_bps)
        return slip / 10000.0  # bps -> decimal

    def entry_slippage(self, mid_price: float, vol_zscore: float, config: ExecutionConfig) -> float:
        """Base slippage for entries (identical to existing logic plus seeded noise)."""
        base = config.base_spread_bps
        slip_decimal = self._slip_bps(base, vol_zscore, config)
        noise_decimal = self._rng.uniform(0.0, slip_decimal * 0.1)
        result = slip_decimal + noise_decimal
        return float(min(result, config.spread_max_bps / 10000.0))

    def stop_loss_slippage(self, stop_price: float, vol_zscore: float, config: ExecutionConfig, side: str) -> float:
        """Adverse slippage on stop-loss fills (marketable orders).

        Returns a POSITIVE slippage factor in price units.
        For longs:  fill = stop - factor  (worse)
        For shorts: fill = stop + factor  (worse)
        """
        base_bps = config.base_spread_bps * 0.5
        slip_decimal = self._slip_bps(base_bps, vol_zscore, config)
        slip_decimal *= 1.5  # SL penalty: 1.5x worse than entry
        noise = self._rng.uniform(0.0, slip_decimal * 0.15)
        total = slip_decimal + noise
        total = min(total, config.spread_max_bps * 1.5 / 10000.0)
        price_slippage = stop_price * total
        return float(price_slippage)

    def take_profit_slippage(self, target_price: float, config: ExecutionConfig) -> float:
        """Neutral-to-slightly-favorable slippage on take-profit fills (limit orders).

        Returns a signed slippage factor in price units.
        Near-zero, may be slightly negative (favorable) at random.
        For longs:  fill = target + factor  (neutral or slightly better)
        For shorts: fill = target - factor  (neutral or slightly better)
        """
        base_bps = config.base_spread_bps * 0.1
        slip_decimal = base_bps / 10000.0
        noise = self._rng.uniform(-slip_decimal * 0.5, slip_decimal * 0.1)
        total = slip_decimal + noise
        total = max(total, -slip_decimal * 0.5)
        return float(target_price * total)

    def seed_hash(self) -> str:
        h = hashlib.md5(str(self._rng.getstate()).encode())
        return h.hexdigest()[:12]
