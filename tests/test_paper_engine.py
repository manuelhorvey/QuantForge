import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from paper_trading.engine import PaperTradingEngine, ExecutionState
from paper_trading.config_manager import EngineConfig
from datetime import datetime
import pytz

@pytest.fixture
def mock_config():
    cfg = EngineConfig()
    cfg.assets = {"EURUSD": {}}
    cfg.capital = 100000
    cfg.portfolio_drawdown_limit = -0.10
    return cfg

@pytest.fixture
def mock_state_store():
    store = MagicMock()
    store.load_snapshot.return_value = None
    return store

@pytest.fixture
def mock_wal():
    return MagicMock()

def test_engine_init(mock_state_store, mock_wal, mock_config):
    with patch("paper_trading.engine.PaperBroker"), \
         patch("paper_trading.engine.ExecutionBridge"), \
         patch("paper_trading.engine.EngineNarrativeService"), \
         patch("paper_trading.engine.EngineRebalanceService"), \
         patch("paper_trading.engine.EngineSatelliteService"), \
         patch("paper_trading.engine.EngineRecoveryService"), \
         patch("paper_trading.engine.EngineStateService"), \
         patch("paper_trading.engine.EngineOrchestrator"), \
         patch("paper_trading.engine.AssetActor"), \
         patch("paper_trading.ops.simulation_snapshot.SimulationStore"), \
         patch("paper_trading.portfolio_builder.build_paper_portfolio", return_value={}), \
         patch("tools.import_guard.verify_feature_pipeline") as mock_verify, \
         patch("paper_trading.engine.ExperimentContext") as mock_exp_ctx:
        
        mock_verify.return_value = {"status": "CLEAN"}
        
        engine = PaperTradingEngine(state_store=mock_state_store, wal_writer=mock_wal, config=mock_config)
        
        assert engine.state_store == mock_state_store
        assert engine.broker is not None
        assert engine.assets == {} # registry builds it

def test_engine_run_once_circuit_breaker(mock_state_store, mock_wal, mock_config):
    with patch("paper_trading.engine.PaperBroker"), \
         patch("paper_trading.engine.ExecutionBridge"), \
         patch("paper_trading.engine.EngineNarrativeService"), \
         patch("paper_trading.engine.EngineRebalanceService"), \
         patch("paper_trading.engine.EngineSatelliteService"), \
         patch("paper_trading.engine.EngineRecoveryService"), \
         patch("paper_trading.engine.EngineStateService"), \
         patch("paper_trading.engine.EngineOrchestrator"), \
         patch("paper_trading.engine.AssetActor"), \
         patch("paper_trading.ops.simulation_snapshot.SimulationStore"), \
         patch("paper_trading.portfolio_builder.build_paper_portfolio", return_value={}), \
         patch("paper_trading.engine.is_market_closed", return_value=False), \
         patch("paper_trading.engine.ExperimentContext"), \
         patch("tools.import_guard.verify_feature_pipeline", return_value={"status": "CLEAN"}):
        
        engine = PaperTradingEngine(state_store=mock_state_store, wal_writer=mock_wal, config=mock_config)
        
        # Simulate drawdown
        engine.portfolio_peak_value = 100000
        engine._state = MagicMock()
        engine._state.compute_mtm_total.return_value = 80000 # 20% drawdown
        
        results = engine.run_once()
        
        assert results["circuit_breaker"]["triggered"] is True
        assert results["circuit_breaker"]["portfolio_drawdown"] == -20.0

def test_engine_run_once_normal(mock_state_store, mock_wal, mock_config):
    with patch("paper_trading.engine.PaperBroker"), \
         patch("paper_trading.engine.ExecutionBridge"), \
         patch("paper_trading.engine.EngineNarrativeService"), \
         patch("paper_trading.engine.EngineRebalanceService"), \
         patch("paper_trading.engine.EngineSatelliteService"), \
         patch("paper_trading.engine.EngineRecoveryService"), \
         patch("paper_trading.engine.EngineStateService"), \
         patch("paper_trading.engine.EngineOrchestrator") as mock_orch_cls, \
         patch("paper_trading.engine.AssetActor"), \
         patch("paper_trading.ops.simulation_snapshot.SimulationStore"), \
         patch("paper_trading.portfolio_builder.build_paper_portfolio", return_value={}), \
         patch("paper_trading.engine.is_market_closed", return_value=False), \
         patch("paper_trading.engine.ExperimentContext"), \
         patch("tools.import_guard.verify_feature_pipeline", return_value={"status": "CLEAN"}):
        
        mock_orch = mock_orch_cls.return_value
        mock_orch.run_once.return_value = {
            "health": {"green": 1},
            "assets": {"EURUSD": {"signal": "BUY"}}
        }
        mock_orch.drain_persist_buffer.return_value = []
        
        engine = PaperTradingEngine(state_store=mock_state_store, wal_writer=mock_wal, config=mock_config)
        engine._state = MagicMock()
        engine._state.compute_mtm_total.return_value = 100000
        
        # Mock services that run_once calls
        engine._narrative = MagicMock()
        engine._rebalance = MagicMock()
        engine._rebalance.should_rebalance.return_value = False
        
        results = engine.run_once()
        
        assert results["EURUSD"]["signal"] == "BUY"
        assert results["orchestrator_health"]["green"] == 1
