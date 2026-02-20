"""
Execution module: order placement, cancel_all, position sizing, circuit breaker.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType

from config import POSITION_SIZE_USD, CIRCUIT_BREAKER_LOSS_USD

logger = logging.getLogger(__name__)


class ExecutionEngine:
    """Handles order execution, risk limits, and circuit breaker."""

    def __init__(
        self,
        client: ClobClient,
        position_size_usd: float = POSITION_SIZE_USD,
        circuit_breaker_loss_usd: float = CIRCUIT_BREAKER_LOSS_USD,
    ):
        self.client = client
        self.position_size_usd = position_size_usd
        self.circuit_breaker_loss_usd = circuit_breaker_loss_usd
        self._session_start_balance: Optional[float] = None
        self._session_pnl: float = 0.0
        self._daily_pnl: float = 0.0
        self._daily_reset_date: Optional[datetime] = None
        self._circuit_breaker_tripped = False

    def _reset_daily_if_needed(self):
        today = datetime.utcnow().date()
        if self._daily_reset_date is None or self._daily_reset_date != today:
            self._daily_pnl = 0.0
            self._daily_reset_date = today

    def record_pnl(self, pnl: float):
        """Record P&L for session and daily tracking."""
        self._session_pnl += pnl
        self._reset_daily_if_needed()
        self._daily_pnl += pnl

        if self._daily_pnl <= -self.circuit_breaker_loss_usd:
            self._circuit_breaker_tripped = True
            logger.critical(
                "CIRCUIT BREAKER: Daily P&L %.2f <= -%.2f. Bot STOPPED.",
                self._daily_pnl,
                self.circuit_breaker_loss_usd,
            )

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

    def cancel_all_orders(self) -> None:
        """Cancel all open orders before starting a new market."""
        try:
            resp = self.client.cancel_all()
            canceled = resp.get("canceled", [])
            not_canceled = resp.get("notCanceled", {})
            if canceled:
                logger.info("Canceled %d orders", len(canceled))
            if not_canceled:
                logger.warning("Could not cancel some orders: %s", not_canceled)
        except Exception as e:
            logger.exception("cancel_all failed: %s", e)

    def place_post_only_limit_order(
        self,
        token_id: str,
        side: str,
        price: float,
        size: float,
    ) -> bool:
        """
        Place a post-only limit order to capture maker rewards.
        Returns True if submitted successfully.
        """
        if self._circuit_breaker_tripped:
            logger.warning("Circuit breaker active. Not placing order.")
            return False

        try:
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size,
                side=side,
            )
            order = self.client.create_order(order_args)
            self.client.post_order(order, orderType=OrderType.GTC, post_only=True)
            logger.info("Posted post-only %s @ %.3f x %.2f", side, price, size)
            return True
        except Exception as e:
            logger.warning("Order failed (may be rejected as marketable): %s", e)
            return False
