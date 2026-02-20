"""
Binance WebSocket feed for real-time BTCUSDT price.
Lead signal for latency arbitrage.
Implements aggressive exponential backoff and auto-reconnect.
"""

import json
import logging
import threading
import time
from typing import Callable, Optional

import websocket

logger = logging.getLogger(__name__)

BINANCE_WS_URL = "wss://stream.binance.com:9443/ws/btcusdt@ticker"

# Exponential backoff: base, max delay, max retries before backing off resets
BACKOFF_BASE_SEC = 1.0
BACKOFF_MAX_SEC = 120.0
BACKOFF_MULTIPLIER = 2.0
PING_INTERVAL = 20
PING_TIMEOUT = 10


class BinancePriceFeed:
    """Real-time BTC price from Binance via WebSocket with resilient reconnection."""

    def __init__(self, on_price: Optional[Callable[[float], None]] = None):
        self._price: Optional[float] = None
        self._prev_price: Optional[float] = None
        self._on_price = on_price
        self._ws: Optional[websocket.WebSocketApp] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._backoff_sec = BACKOFF_BASE_SEC
        self._reconnect_count = 0

    def _on_message(self, _, message: str):
        try:
            data = json.loads(message)
            p = float(data.get("c", 0))
            if p > 0:
                self._prev_price = self._price
                self._price = p
                if self._on_price:
                    self._on_price(p)
                # Reset backoff on successful message
                self._backoff_sec = BACKOFF_BASE_SEC
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.debug("Binance message parse error: %s", e)

    def _on_error(self, ws, error):
        logger.warning("Binance WebSocket error: %s", error)

    def _on_close(self, ws, close_status_code, close_msg):
        if self._running:
            logger.info(
                "Binance WebSocket closed (code=%s, msg=%s). Reconnecting...",
                close_status_code,
                close_msg,
            )

    def _run_ws(self):
        while self._running:
            try:
                self._ws = websocket.WebSocketApp(
                    BINANCE_WS_URL,
                    on_message=self._on_message,
                    on_error=self._on_error,
                    on_close=self._on_close,
                )
                self._ws.run_forever(
                    ping_interval=PING_INTERVAL,
                    ping_timeout=PING_TIMEOUT,
                )
            except Exception as e:
                logger.warning("Binance WebSocket exception: %s", e)

            if not self._running:
                break

            # Exponential backoff before reconnect
            self._reconnect_count += 1
            delay = min(self._backoff_sec, BACKOFF_MAX_SEC)
            logger.info(
                "Binance reconnect #%d: waiting %.1fs before retry",
                self._reconnect_count,
                delay,
            )
            time.sleep(delay)
            self._backoff_sec = min(
                self._backoff_sec * BACKOFF_MULTIPLIER,
                BACKOFF_MAX_SEC,
            )

    def start(self):
        """Start the WebSocket feed."""
        if self._running:
            return
        self._running = True
        self._backoff_sec = BACKOFF_BASE_SEC
        self._reconnect_count = 0
        self._thread = threading.Thread(target=self._run_ws, daemon=True)
        self._thread.start()
        # Brief wait for first price
        for _ in range(50):
            if self._price is not None:
                break
            time.sleep(0.1)

    def stop(self):
        """Stop the WebSocket feed."""
        self._running = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=3)

    @property
    def price(self) -> Optional[float]:
        return self._price

    @property
    def prev_price(self) -> Optional[float]:
        return self._prev_price

    def price_change_pct(self) -> Optional[float]:
        """Return recent price change in percent, or None."""
        if self._price is None or self._prev_price is None or self._prev_price <= 0:
            return None
        return (self._price - self._prev_price) / self._prev_price * 100.0
