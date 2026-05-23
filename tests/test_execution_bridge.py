import pytest

from execution.paper_broker import PaperBroker
from paper_trading.execution_bridge import ExecutionBridge
from shared.execution_config import ExecutionConfig


def test_fill_price_buy_worse_than_mid():
    config = ExecutionConfig(base_spread_bps=10.0, spread_vol_slope=2.0, impact_model="none")
    broker = PaperBroker(execution_configs={"EURUSD=X": config})
    bridge = ExecutionBridge(broker)
    fill, slip_bps, impact_bps = bridge.fill_price("EURUSD=X", "buy", 10000, 1.10)
    assert fill > 1.10
    assert slip_bps >= 0
    assert impact_bps == 0.0


def test_estimate_impact_bps_square_root():
    config = ExecutionConfig(
        impact_model="square_root",
        impact_coeff=0.1,
        avg_daily_volume=1_000_000,
        base_spread_bps=0.0,
        spread_vol_slope=0.0,
    )
    broker = PaperBroker(execution_configs={"AAPL": config})
    bridge = ExecutionBridge(broker)
    bps = bridge.estimate_impact_bps("AAPL", 100_000)
    assert bps > 0
