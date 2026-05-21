import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import yaml

logger = logging.getLogger("quantforge.config_manager")

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "configs",
    "paper_trading.yaml",
)


def _default_halt() -> dict:
    return {
        "drawdown": -0.08,
        "monthly_pf": 0.70,
        "signal_drought": 30,
        "prob_drift": 0.15,
    }


@dataclass
class EngineConfig:
    capital: float = 100_000
    position_size: float = 0.95
    rebalance: str = "daily"
    retrain_freq: str = "annual"
    retrain_window: int = 5
    research_mode: bool = False
    halt: dict = field(default_factory=_default_halt)
    satellite: dict = field(default_factory=dict)
    assets: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict) -> "EngineConfig":
        halt = dict(data.get("halt", _default_halt()))
        # Ensure halt has all expected keys
        defaults = _default_halt()
        for k, v in defaults.items():
            halt.setdefault(k, v)
        return cls(
            capital=data.get("capital", 100_000),
            position_size=data.get("position_size", 0.95),
            rebalance=data.get("rebalance", "daily"),
            retrain_freq=data.get("retrain_freq", "annual"),
            retrain_window=data.get("retrain_window", 5),
            research_mode=data.get("research_mode", False),
            halt=halt,
            satellite=data.get("satellite", {}),
            assets=data.get("assets", {}),
        )

    def to_dict(self) -> dict:
        return {
            "capital": self.capital,
            "position_size": self.position_size,
            "rebalance": self.rebalance,
            "retrain_freq": self.retrain_freq,
            "retrain_window": self.retrain_window,
            "research_mode": self.research_mode,
            "halt": self.halt,
            "satellite": self.satellite,
            "assets": self.assets,
        }


def load_config(path: Optional[str] = None) -> EngineConfig:
    path = path or DEFAULT_CONFIG_PATH
    if os.path.exists(path):
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        logger.info("Loaded config from %s", path)
        return EngineConfig.from_dict(data)
    logger.warning("Config file %s not found; using defaults", path)
    return EngineConfig()
