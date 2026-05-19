from abc import ABC, abstractmethod
import numpy as np
import pandas as pd


class PositionSizingStrategy(ABC):
    @abstractmethod
    def compute(self, close: pd.Series, config: dict) -> float:
        ...


class VolTargetSizing(PositionSizingStrategy):
    def __init__(self, window: int = 30, target_vol: float = 0.30):
        self.window = window
        self.target_vol = target_vol

    def compute(self, close: pd.Series, config: dict) -> float:
        if not config.get("vol_scalar"):
            return 1.0
        rets = close.pct_change().dropna()
        if len(rets) < self.window:
            return 1.0
        rv = rets.iloc[-self.window:].std() * np.sqrt(252)
        if pd.isna(rv) or np.isinf(rv):
            return 1.0
        scalar = self.target_vol / (rv + 1e-9)
        return min(scalar, 1.0)
