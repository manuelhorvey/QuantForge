import pytest
from execution.paper_broker import PaperBroker
from execution.broker_interface import Order


@pytest.fixture
def priced_broker():
    b = PaperBroker(initial_capital=100000, slippage=0.0, fees=0.0)
    b.set_price("TEST", 100.0)
    b.set_price("ASSET_A", 50.0)
    b.set_price("ASSET_B", 100.0)
    return b


class TestPaperBroker:
    @pytest.fixture
    def broker(self):
        return PaperBroker(initial_capital=100000, slippage=0.0, fees=0.0)

    def test_initial_state(self, broker):
        summary = broker.get_account_summary()
        assert summary.total_cash == 100000
        assert summary.buying_power == 200000
        assert summary.portfolio_value == 100000
        assert len(summary.positions) == 0

    def test_connect_disconnect(self, broker):
        assert broker.connect() is True
        assert broker.disconnect() is True

    def test_get_current_price_returns_zero_for_unknown(self, broker):
        price = broker.get_current_price("NONEXISTENT_SYMBOL_12345")
        assert price == 0.0

    def test_place_buy_order_insufficient_cash(self, priced_broker):
        order = Order(asset="TEST", side="buy", quantity=1e9, order_type="market")
        order_id = priced_broker.place_order(order)
        assert order_id != ""
        summary = priced_broker.get_account_summary()
        assert summary.total_cash < 100000

    def test_place_sell_no_position(self, broker):
        order = Order(asset="TEST", side="sell", quantity=100, order_type="market")
        order_id = broker.place_order(order)
        assert order_id == ""

    def test_cancel_order(self, broker):
        assert broker.cancel_order("1") is False

    def test_get_order_status_unknown(self, broker):
        assert broker.get_order_status("999") == "unknown"

    def test_get_positions_empty(self, broker):
        assert broker.get_positions() == []

    def test_refresh_prices_empty(self, broker):
        broker.refresh_prices()

    def test_reset(self, priced_broker):
        priced_broker.place_order(Order(asset="TEST", side="buy", quantity=10, order_type="market"))
        priced_broker.reset(capital=50000)
        assert priced_broker.initial_capital == 50000
        assert priced_broker.cash == 50000
        assert len(priced_broker._positions) == 0

    def test_buy_order_fills_and_tracks_position(self, priced_broker):
        order = Order(asset="TEST", side="buy", quantity=10, order_type="market")
        order_id = priced_broker.place_order(order)
        assert order_id != ""
        assert order.status == "filled"
        positions = priced_broker.get_positions()
        assert len(positions) == 1
        assert positions[0].quantity == 10

    def test_sell_reduces_position(self, priced_broker):
        priced_broker.place_order(Order(asset="TEST", side="buy", quantity=10, order_type="market"))
        cash_after_buy = priced_broker.get_account_summary().total_cash
        priced_broker.place_order(Order(asset="TEST", side="sell", quantity=5, order_type="market"))
        assert priced_broker.get_account_summary().total_cash > cash_after_buy

    def test_dual_positions(self, priced_broker):
        priced_broker.place_order(Order(asset="ASSET_A", side="buy", quantity=10, order_type="market"))
        priced_broker.place_order(Order(asset="ASSET_B", side="buy", quantity=20, order_type="market"))
        summary = priced_broker.get_account_summary()
        assert len(summary.positions) == 2
