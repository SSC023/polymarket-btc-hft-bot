"""
Polymarket Order Book WebSocket feed.
Provides real-time best bid/ask and mid_price for market making.
"""

import json
import logging
import threading
import time
from typing import Callable, Optional

import websocket

from config import POLYMARKET_WS_URL

logger = logging.getLogger(__name__)

PING_INTERVAL = 10
BACKOFF_BASE = 1.0
BACKOFF_MAX = 60.0
BACKOFF_MULT = 2.0


class OrderBookFeed:
    """
    Polymarket Order Book WebSocket with exponential backoff reconnect.
    Subscribes to Yes token for best_bid_ask and book updates.
    """

    def __init__(
        self,
        yes_token_id: str,
        no_token_id: str,
        on_mid_price: Optional[Callable[[float, float, float], None]] = None,
    ):
        self._yes_token_id = yes_token_id
        self._no_token_id = no_token_id
        self._on_mid_price = on_mid_price
        self._best_bid: Optional[float] = None
        self._best_ask: Optional[float] = None
        self._mid_price: Optional[float] = None
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._backoff = BACKOFF_BASE

    def _on_message(self, _, message: str):
        try:
            data = json.loads(message)
            if isinstance(data, dict):
                self._process_message(data)
        except (json.JSONDecodeError, TypeError) as e:
            logger.debug("OrderBook parse error: %s", e)

    def _process_message(self, data: dict):
        """Update best bid/ask from book or best_bid_ask events."""
        event_type = data.get("event_type")

        if event_type == "best_bid_ask":
            bid = data.get("best_bid")
            ask = data.get("best_ask")
            if bid is not None and ask is not None:
                self._update_book(float(bid), float(ask))
            return

        if event_type == "book":
            asset_id = str(data.get("asset_id", ""))
            if asset_id != self._yes_token_id:
                return
            bids = data.get("bids") or []
            asks = data.get("asks") or []
            best_bid = float(bids[0]["price"]) if bids else None
            best_ask = float(asks[0]["price"]) if asks else None
            if best_bid is not None and best_ask is not None:
                self._update_book(best_bid, best_ask)
            return

        if event_type == "price_change":
            changes = data.get("price_changes") or []
            for pc in changes:
                if str(pc.get("asset_id")) == self._yes_token_id:
                    bid = pc.get("best_bid")
                    ask = pc.get("best_ask")
                    if bid is not None and ask is not None:
                        try:
                            b, a = float(bid), float(ask)
                            if b > 0 and a > 0 and a < 2:
                                self._update_book(b, a)
                        except (ValueError, TypeError):
                            pass
                    break

    def _update_book(self, best_bid: float, best_ask: float):
        """Update internal state and compute mid."""
        self._best_bid = best_bid
        self._best_ask = best_ask
        self._mid_price = (best_bid + best_ask) / 2.0 if (best_bid and best_ask) else None
        self._backoff = BACKOFF_BASE
        if self._mid_price is not None and self._on_mid_price:
            self._on_mid_price(self._mid_price, best_bid, best_ask)

    def _run_ws(self):
        while self._running:
            try:
                self._ws = websocket.WebSocketApp(
                    POLYMARKET_WS_URL,
                    on_message=self._on_message,
                    on_error=lambda _, e: logger.warning("OrderBook WS error: %s", e),
                    on_close=lambda *_: logger.info("OrderBook WS closed"),
                )
                self._ws.on_open = self._on_open
                self._ws.run_forever(ping_interval=PING_INTERVAL, ping_timeout=5)
            except Exception as e:
                logger.warning("OrderBook WS exception: %s", e)
            if not self._running:
                break
            delay = min(self._backoff, BACKOFF_MAX)
            logger.info("OrderBook reconnect in %.1fs", delay)
            time.sleep(delay)
            self._backoff = min(self._backoff * BACKOFF_MULT, BACKOFF_MAX)

    def _on_open(self, ws):
        """Subscribe to Yes and No tokens."""
        msg = json.dumps({
            "assets_ids": [self._yes_token_id, self._no_token_id],
            "type": "market",
            "custom_feature_enabled": True,
        })
        ws.send(msg)

    def start(self):
        """Start WebSocket feed."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run_ws, daemon=True)
        self._thread.start()
        for _ in range(100):
            if self._mid_price is not None:
                break
            time.sleep(0.1)

    def stop(self):
        """Stop WebSocket feed."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=3)

    @property
    def best_bid(self) -> Optional[float]:
        return self._best_bid

    @property
    def best_ask(self) -> Optional[float]:
        return self._best_ask

    @property
    def mid_price(self) -> Optional[float]:
        return self._mid_price
