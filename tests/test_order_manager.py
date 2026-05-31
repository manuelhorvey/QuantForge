import pytest
from unittest.mock import MagicMock
from paper_trading.execution.order_manager import OrderManager
from paper_trading.execution.broker_interface import Order

@pytest.fixture
def mock_broker():
    return MagicMock()

def test_order_manager_init(mock_broker):
    om = OrderManager(mock_broker)
    assert om.broker == mock_broker
    assert len(om.pending_orders) == 0

def test_submit_market_order(mock_broker):
    mock_broker.place_order.return_value = "order_1"
    om = OrderManager(mock_broker)
    order_id = om.submit_market_order("EURUSD", "buy", 1000)
    assert order_id == "order_1"
    assert "order_1" in om.pending_orders
    assert om.pending_orders["order_1"].side == "buy"

def test_submit_market_order_prefilled(mock_broker):
    mock_broker.place_filled_order.return_value = "order_2"
    om = OrderManager(mock_broker)
    order_id = om.submit_market_order("EURUSD", "sell", 500, fill_price=1.10)
    assert order_id == "order_2"
    assert "order_2" in om.pending_orders
    mock_broker.place_filled_order.assert_called_once()

def test_submit_limit_order(mock_broker):
    mock_broker.place_order.return_value = "order_3"
    om = OrderManager(mock_broker)
    order_id = om.submit_limit_order("EURUSD", "buy", 1000, 1.09)
    assert order_id == "order_3"
    assert om.pending_orders["order_3"].order_type == "limit"
    assert om.pending_orders["order_3"].limit_price == 1.09

def test_cancel_order(mock_broker):
    mock_broker.place_order.return_value = "order_4"
    om = OrderManager(mock_broker)
    om.submit_market_order("EURUSD", "buy", 1000)
    
    mock_broker.cancel_order.return_value = True
    success = om.cancel_order("order_4")
    assert success is True
    assert "order_4" not in om.pending_orders
    assert len(om.cancelled_orders) == 1

def test_cancel_missing_order(mock_broker):
    om = OrderManager(mock_broker)
    success = om.cancel_order("missing")
    assert success is False

def test_check_pending_orders(mock_broker):
    om = OrderManager(mock_broker)
    mock_broker.place_order.side_effect = ["o1", "o2"]
    om.submit_market_order("EURUSD", "buy", 1000)
    om.submit_market_order("EURUSD", "sell", 500)
    
    mock_broker.get_order_status.side_effect = ["filled", "pending"]
    filled = om.check_pending_orders()
    assert len(filled) == 1
    assert filled[0].order_id == "o1"
    assert "o1" not in om.pending_orders
    assert "o2" in om.pending_orders

def test_get_open_quantity(mock_broker):
    om = OrderManager(mock_broker)
    mock_broker.place_order.side_effect = ["o1", "o2", "o3"]
    om.submit_market_order("EURUSD", "buy", 1000)
    om.submit_market_order("EURUSD", "buy", 500)
    om.submit_market_order("EURUSD", "sell", 300)
    
    assert om.get_open_quantity("EURUSD") == 1200 # 1000 + 500 - 300
    assert om.has_pending is True
