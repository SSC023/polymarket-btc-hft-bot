"""
Execution module: Order Manager, inventory limits, cancel_all, circuit breaker.
"""

import logging
from datetime import datetime
from typing import Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType

from config import (
    POSITION_SIZE_USD,
    CIRCUIT_BREAKER_LOSS_USD,
    MAX_INVENTORY_YES,
    MAX_INVENTORY_NO,
    MID_PRICE_DRIFT_THRESHOLD,
)

logger = logging.getLogger(__name__)


class OrderManager:
    """
    Order Manager with inventory management and mid-price drift detection.
    Re-quotes when mid_price drifts > threshold. Enforces inventory limits.
    """

    def __init__(
        self,
        client: ClobClient,
        position_size_usd: float = POSITION_SIZE_USD,
        circuit_breaker_loss_usd: float = CIRCUIT_BREAKER_LOSS_USD,
        max_inventory_yes: int = MAX_INVENTORY_YES,
        max_inventory_no: int = MAX_INVENTORY_NO,
        mid_drift_threshold: float = MID_PRICE_DRIFT_THRESHOLD,
    ):
        self.client = client
        self.position_size_usd = position_size_usd
        self.circuit_breaker_loss_usd = circuit_breaker_loss_usd
        self.max_inventory_yes = max_inventory_yes
        self.max_inventory_no = max_inventory_no
        self.mid_drift_threshold = mid_drift_threshold
        self._session_pnl: float = 0.0
        self._daily_pnl: float = 0.0
        self._daily_reset_date: Optional[datetime] = None
        self._circuit_breaker_tripped = False
        self._inventory_yes: float = 0.0
        self._inventory_no: float = 0.0
        self._last_mid_price: Optional[float] = None
        self._active_yes_bid: Optional[tuple[float, float]] = None  # (price, size)
        self._active_no_bid: Optional[tuple[float, float]] = None

    def _reset_daily_if_needed(self):
        today = datetime.utcnow().date()
        if self._daily_reset_date is None or self._daily_reset_date != today:
            self._daily_pnl = 0.0
            self._daily_reset_date = today

    def record_pnl(self, pnl: float):
        self._session_pnl += pnl
        self._reset_daily_if_needed()
        self._daily_pnl += pnl
        if self._daily_pnl <= -self.circuit_breaker_loss_usd:
            self._circuit_breaker_tripped = True
            logger.critical("CIRCUIT BREAKER: Daily P&L %.2f <= -%.2f. Bot STOPPED.", self._daily_pnl, self.circuit_breaker_loss_usd)

    def record_fill(self, outcome: str, size: float, price: float):
        """Record a fill to update inventory."""
        if outcome == "Yes":
            self._inventory_yes += size
        else:
            self._inventory_no += size

    @property
    def circuit_breaker_tripped(self) -> bool:
        return self._circuit_breaker_tripped

    @property
    def session_pnl(self) -> float:
        return self._session_pnl

    @property
    def daily_pnl(self) -> float:
        self._reset_daily_if_needed()
        return self._daily_pnl

    @property
    def inventory_yes(self) -> float:
        return self._inventory_yes

    @property
    def inventory_no(self) -> float:
        return self._inventory_no

    @property
    def active_yes_bid(self) -> Optional[tuple[float, float]]:
        return self._active_yes_bid

    @property
    def active_no_bid(self) -> Optional[tuple[float, float]]:
        return self._active_no_bid

    def should_requote(self, current_mid: float) -> bool:
        """True if mid_price has drifted more than threshold."""
        if self._last_mid_price is None:
            return True
        return abs(current_mid - self._last_mid_price) > self.mid_drift_threshold

    def set_last_mid(self, mid: float):
        self._last_mid_price = mid

    def can_quote_yes(self) -> bool:
        return self._inventory_yes < self.max_inventory_yes

    def can_quote_no(self) -> bool:
        return self._inventory_no < self.max_inventory_no

    def cancel_all_orders(self) -> None:
        """Cancel all open orders."""
        try:
            resp = self.client.cancel_all()
            canceled = resp.get("canceled", [])
            self._active_yes_bid = None
            self._active_no_bid = None
            if canceled:
                logger.info("Canceled %d orders", len(canceled))
        except Exception as e:
            logger.exception("cancel_all failed: %s", e)

    def place_post_only_limit_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
        outcome: str = "",
    ) -> bool:
        """Place post-only limit order. Returns True if submitted."""
        if self._circuit_breaker_tripped:
            return False
        try:
            order_args = OrderArgs(token_id=token_id, price=price, size=size, side=side)
            order = self.client.create_order(order_args)
            self.client.post_order(order, orderType=OrderType.GTC, post_only=True)
            if outcome == "Yes":
                self._active_yes_bid = (price, size)
            elif outcome == "No":
                self._active_no_bid = (price, size)
            logger.info("Posted post-only %s @ %.3f x %.2f", side, price, size)
            return True
        except Exception as e:
            logger.warning("Order failed: %s", e)
            return False

    def clear_active_bid(self, outcome: str):
        if outcome == "Yes":
            self._active_yes_bid = None
        elif outcome == "No":
            self._active_no_bid = None
