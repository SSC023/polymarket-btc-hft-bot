"""
Passive Market Making Strategy.
Symmetrical Post-Only Limit Orders on both sides of the book.
Yes bid at mid_price - target_spread, No bid at (1 - mid_price) - target_spread.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from config import TARGET_SPREAD

logger = logging.getLogger(__name__)


@dataclass
class QuoteSignal:
    """Signal to place a post-only bid on Yes or No."""

    token_id: str
    side: str  # "BUY"
    outcome: str  # "Yes" or "No"
    price: float
    size: float


class MarketMakerStrategy:
    """
    Calculates symmetrical quotes around mid_price.
    Yes bid = mid - spread, No bid = (1 - mid) - spread.
    """

    def __init__(self, target_spread: float = TARGET_SPREAD):
        self.target_spread = target_spread

    def get_quotes(
        self,
        mid_price: float,
        yes_token_id: str,
        no_token_id: str,
        size: float,
        quote_yes: bool = True,
        quote_no: bool = True,
    ) -> list["QuoteSignal"]:
        """
        Return list of QuoteSignals for symmetrical bids.
        quote_yes/quote_no: set False if inventory limit reached on that side.
        """
        if mid_price <= 0 or mid_price >= 1:
            return []
        signals = []
        yes_bid = round(mid_price - self.target_spread, 3)
        no_bid = round((1.0 - mid_price) - self.target_spread, 3)

        if quote_yes and 0.01 <= yes_bid <= 0.99 and size >= 1:
            signals.append(QuoteSignal(
                token_id=yes_token_id,
                side="BUY",
                outcome="Yes",
                price=yes_bid,
                size=size,
            ))
        if quote_no and 0.01 <= no_bid <= 0.99 and size >= 1:
            signals.append(QuoteSignal(
                token_id=no_token_id,
                side="BUY",
                outcome="No",
                price=no_bid,
                size=size,
            ))
        return signals
