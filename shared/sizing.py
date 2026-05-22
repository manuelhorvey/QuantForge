from abc import ABC, abstractmethod
import numpy as np
import pandas as pd


class PositionSizingStrategy(ABC):
    @abstractmethod
    def compute(self, close: pd.Series, config: dict) -> float:
        ...


class VolTargetSizing(PositionSizingStrategy):
    def __init__(self, window: int = 30, target_vol: float = 0.30, regime_aware: bool = False):
        self.window = window
        self.target_vol = target_vol
        self.regime_aware = regime_aware

    def compute(self, close: pd.Series, config: dict, regime: str = "neutral") -> float:
        if not config.get("vol_scalar"):
            return 1.0
        
        target = self.target_vol
        if self.regime_aware:
            # Plan: CALM (range) expands to 1.2x target, CRISIS (volatile) contracts to 0.5x
            multipliers = {
                "range": 1.2,
                "trend": 1.0,
                "volatile": 0.5,
                "neutral": 1.0
            }
            target *= multipliers.get(regime, 1.0)
            
        rets = close.pct_change().dropna()
        if len(rets) < self.window:
            return 1.0
        rv = rets.iloc[-self.window:].std() * np.sqrt(252)
        if pd.isna(rv) or np.isinf(rv):
            return 1.0
        scalar = target / (rv + 1e-9)
        return min(scalar, 1.0)

    def edge_decay(self, impact_bps: float, threshold_bps: float = 5.0) -> float:
        """Scales down position size when estimated impact exceeds a threshold."""
        if impact_bps > threshold_bps:
            return 0.5
        return 1.0
