import logging
from datetime import datetime
from typing import Dict, List, Optional
import yfinance as yf

from execution.broker_interface import BrokerInterface, Order, Position, AccountSummary

logger = logging.getLogger("quantforge.paper_broker")


class PaperBroker(BrokerInterface):
    """
    Simulated broker that fills market orders at yfinance prices.
    Designed to be intentionally simple: no partial fills, no order books.
    """

    def __init__(
        self,
        initial_capital: float = 100_000,
        slippage: float = 0.001,
        fees: float = 0.0,
    ):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.slippage = slippage
        self.fees = fees
        self._positions: Dict[str, Position] = {}
        self._orders: Dict[str, Order] = {}
        self._next_order_id = 1
        self._price_cache: Dict[str, float] = {}

    def connect(self) -> bool:
        return True

    def disconnect(self) -> bool:
        return True

    def get_account_summary(self) -> AccountSummary:
        positions = list(self._positions.values())
        portfolio_value = self.cash + sum(
            p.quantity * p.current_price for p in positions
        )
        buying_power = self.cash * 2
        return AccountSummary(
            total_cash=round(self.cash, 2),
            buying_power=round(buying_power, 2),
            portfolio_value=round(portfolio_value, 2),
            positions=positions,
        )

    def place_order(self, order: Order) -> str:
        price = self.get_current_price(order.asset)
        if price <= 0:
            logger.error("Invalid price %s for %s", price, order.asset)
            return ""

        fill_price = price * (1 + self.slippage) if order.side == "buy" else price * (1 - self.slippage)
        fill_qty = order.quantity
        cost = fill_price * fill_qty
        fee = cost * self.fees

        if order.side == "buy":
            total_required = cost + fee
            if total_required > self.cash:
                fill_qty = self.cash / (fill_price * (1 + self.fees))
                cost = fill_price * fill_qty
                fee = cost * self.fees
                logger.info("Order partially filled: %s qty reduced to %.4f", order.asset, fill_qty)
            self.cash -= cost + fee
            self._update_position(order.asset, fill_qty, fill_price)
        elif order.side == "sell":
            pos = self._positions.get(order.asset)
            if pos is None or pos.quantity <= 0:
                logger.warning("No position to sell for %s", order.asset)
                return ""
            sell_qty = min(fill_qty, pos.quantity)
            realized = (fill_price - pos.avg_entry_price) * sell_qty - fee
            pos.realized_pnl += realized
            pos.quantity -= sell_qty
            self.cash += fill_price * sell_qty - fee
            if pos.quantity <= 0:
                del self._positions[order.asset]

        order_id = str(self._next_order_id)
        self._next_order_id += 1
        order.order_id = order_id
        order.status = "filled"
        order.timestamp = datetime.now()
        self._orders[order_id] = order
        logger.debug("Order %s: %s %s %.4f @ %.2f", order_id, order.side, order.asset, fill_qty, fill_price)
        return order_id

    def cancel_order(self, order_id: str) -> bool:
        return False

    def get_order_status(self, order_id: str) -> str:
        order = self._orders.get(order_id)
        return order.status if order else "unknown"

    def get_positions(self) -> List[Position]:
        return list(self._positions.values())

    def get_current_price(self, asset: str) -> float:
        if asset in self._price_cache:
            return self._price_cache[asset]
        try:
            ticker = yf.Ticker(asset)
            data = ticker.history(period="1d")
            if not data.empty:
                price = float(data["Close"].iloc[-1])
                self._price_cache[asset] = price
                return price
        except Exception as e:
            logger.warning("Price fetch failed for %s: %s", asset, e)
        return 0.0

    def _update_position(self, asset: str, quantity: float, price: float) -> None:
        if quantity <= 0:
            return
        if asset in self._positions:
            pos = self._positions[asset]
            total_qty = pos.quantity + quantity
            total_cost = pos.avg_entry_price * pos.quantity + price * quantity
            pos.avg_entry_price = total_cost / total_qty
            pos.quantity = total_qty
        else:
            self._positions[asset] = Position(
                asset=asset,
                quantity=quantity,
                avg_entry_price=price,
                current_price=price,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
            )

    def refresh_prices(self) -> None:
        for asset in list(self._positions.keys()):
            price = self.get_current_price(asset)
            if price > 0:
                pos = self._positions[asset]
                pos.current_price = price
                pos.unrealized_pnl = (price - pos.avg_entry_price) * pos.quantity

    def set_price(self, asset: str, price: float) -> None:
        self._price_cache[asset] = price

    def reset(self, capital: float = 100_000) -> None:
        self.initial_capital = capital
        self.cash = capital
        self._positions.clear()
        self._orders.clear()
        self._next_order_id = 1
        self._price_cache.clear()
