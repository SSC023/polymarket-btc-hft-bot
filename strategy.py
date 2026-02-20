"""
Latency Arbitrage Strategy.
Lead: Binance BTC price. Lag: Polymarket Yes share price.
Trigger: Binance jump >0.1%, Polymarket stale, EV > 1.02.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from py_clob_client.clob_types import OrderArgs, OrderType

from config import BINANCE_JUMP_THRESHOLD_PCT, EV_THRESHOLD

logger = logging.getLogger(__name__)


@dataclass
class TradeSignal:
    """Signal to place a post-only limit order."""

    token_id: str  # Yes token
    side: str  # "BUY"
    price: float
    size: float  # in USDC
    ev: float


class LatencyArbitrageStrategy:
    """
    When Binance jumps >threshold but Polymarket Yes hasn't moved,
    compute EV. If EV > threshold, emit buy signal (post-only).
    """

    def __init__(
        self,
        jump_threshold_pct: float = BINANCE_JUMP_THRESHOLD_PCT,
        ev_threshold: float = EV_THRESHOLD,
    ):
        self.jump_threshold_pct = jump_threshold_pct
        self.ev_threshold = ev_threshold
        self._last_poly_yes_price: Optional[float] = None
        self._poly_price_stale_threshold = 0.0005  # consider "not moved" if change < this

    def check_signal(
        self,
        yes_token_id: str,
        binance_price: float,
        binance_prev_price: Optional[float],
        binance_change_pct: Optional[float],
        poly_yes_price: float,
        position_size_usd: float,
    ) -> Optional[TradeSignal]:
        """
        Check if we should place a BUY order on Yes.
        - Binance must have jumped > jump_threshold_pct
        - Polymarket Yes price considered stale (we use current as baseline for simplicity)
        - EV = (implied_win_prob) / yes_price > ev_threshold
        """
        if poly_yes_price <= 0 or poly_yes_price >= 1:
            return None

        # Need positive Binance move
        if binance_change_pct is None or binance_change_pct < self.jump_threshold_pct:
            return None

        # Implied win prob: bump based on Binance lead. More jump -> higher implied
        bump = min(0.08, (binance_change_pct / 100) * 2)  # e.g. 0.2% move -> 0.004 bump
        implied_prob = min(0.99, poly_yes_price + bump)

        # EV = payout if win / cost. Cost = price, payout = 1. So EV = implied_prob / price
        ev = implied_prob / poly_yes_price if poly_yes_price > 0 else 0

        if ev < self.ev_threshold:
            return None

        # Size: position_size_usd / price = number of shares
        num_shares = position_size_usd / poly_yes_price
        # Round to 2 decimals for order size
        size = round(num_shares, 2)
        if size < 1:
            return None

        return TradeSignal(
            token_id=yes_token_id,
            side="BUY",
            price=round(poly_yes_price, 3),
            size=size,
            ev=ev,
        )
