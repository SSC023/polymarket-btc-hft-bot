"""
24/7 Market Discovery - Gamma API Scanner for BTC 15-minute markets.
Polls Gamma API, finds active market, and switches to next when current ends.
"""

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

import requests

from config import GAMMA_EVENTS_URL, GAMMA_API_URL, BTC_15M_SLUG

logger = logging.getLogger(__name__)


@dataclass
class ActiveMarket:
    """Represents the current active BTC 15m market."""

    event_id: str
    event_slug: str
    market_id: str
    question: str
    end_date_iso: str
    yes_token_id: str
    no_token_id: str
    accepting_orders: bool


class Scanner:
    """
    Polls Gamma API for BTC 15-minute Up/Down markets.
    Search: tag 'Bitcoin' + '15-minute' in title, or slug 'bitcoin-price-15-minute'.
    """

    POLL_INTERVAL = 30  # seconds
    REQUEST_TIMEOUT = 15

    def __init__(self):
        self._last_event_data: Optional[dict] = None
        self._last_market: Optional[ActiveMarket] = None

    def _fetch_events(self, slug: Optional[str] = None, tag_slug: Optional[str] = None) -> list:
        """Fetch events from Gamma API with optional filters."""
        params = {
            "active": "true",
            "closed": "false",
            "limit": 100,
        }
        if slug:
            params["slug"] = slug
        if tag_slug:
            params["tag_slug"] = tag_slug

        try:
            r = requests.get(GAMMA_EVENTS_URL, params=params, timeout=self.REQUEST_TIMEOUT)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            logger.warning("Gamma API request failed: %s", e)
            return []

    def _find_btc_15m_event(self) -> Optional[dict]:
        """
        Find the BTC 15-minute event.
        Priority: 1) slug=bitcoin-price-15-minute, 2) tag + title search.
        """
        # Try slug first (fallback when Polymarket changes series ID)
        result = self._fetch_events(slug=BTC_15M_SLUG)
        if result:
            ev = result[0] if isinstance(result, list) else result
            return ev

        # Fallback: fetch with tag and filter by title
        events = self._fetch_events(tag_slug="bitcoin")
        for ev in events:
            title = (ev.get("title") or "").lower()
            if "15-minute" in title or "15 minute" in title:
                return ev

        # Also try slug_contains
        try:
            r = requests.get(
                GAMMA_EVENTS_URL,
                params={
                    "active": "true",
                    "closed": "false",
                    "slug_contains": "bitcoin",
                    "limit": 50,
                },
                timeout=self.REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            for ev in r.json():
                title = (ev.get("title") or "").lower()
                slug = (ev.get("slug") or "").lower()
                if "15-minute" in title or "15 minute" in title or "15-minute" in slug:
                    return ev
        except requests.RequestException:
            pass

        return None

    def _parse_clob_token_ids(self, raw: str) -> tuple[str, str]:
        """Parse clobTokenIds JSON string. Returns (yes_token_id, no_token_id)."""
        try:
            ids = json.loads(raw)
            if isinstance(ids, list) and len(ids) >= 2:
                return str(ids[0]), str(ids[1])
        except (json.JSONDecodeError, TypeError):
            pass
        return "", ""

    def _get_active_market_from_event(self, event: dict) -> Optional[ActiveMarket]:
        """From event, find the current active (not closed) market with nearest end_date."""
        markets = event.get("markets") or []
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        active_markets = []
        for m in markets:
            if m.get("closed"):
                continue
            if not m.get("acceptingOrders", True):
                continue
            end = m.get("endDate") or m.get("endDateIso") or ""
            if end and end < now_iso:
                continue
            yes_id, no_id = self._parse_clob_token_ids(m.get("clobTokenIds") or "[]")
            if not yes_id or not no_id:
                continue
            active_markets.append((m, end))

        if not active_markets:
            return None

        # Pick market with earliest end_date (current window)
        active_markets.sort(key=lambda x: x[1] or "9999")
        m, end = active_markets[0]
        yes_id, no_id = self._parse_clob_token_ids(m.get("clobTokenIds") or "[]")

        return ActiveMarket(
            event_id=str(event.get("id", "")),
            event_slug=str(event.get("slug", "")),
            market_id=str(m.get("id", "")),
            question=str(m.get("question", "")),
            end_date_iso=end or "",
            yes_token_id=yes_id,
            no_token_id=no_id,
            accepting_orders=bool(m.get("acceptingOrders", True)),
        )

    def get_active_market(self) -> Optional[ActiveMarket]:
        """
        Get the current active BTC 15-minute market.
        Returns None if none found (e.g. between windows).
        """
        event = self._find_btc_15m_event()
        if not event:
            return None
        self._last_event_data = event
        market = self._get_active_market_from_event(event)
        self._last_market = market
        return market

    def get_market_resolution(self, market_id: str) -> Optional[bool]:
        """
        Fetch resolved market from Gamma API.
        Returns True if Yes won, False if No won, None if not resolved or error.
        """
        url = f"{GAMMA_API_URL}/markets/{market_id}"
        try:
            r = requests.get(url, timeout=self.REQUEST_TIMEOUT)
            r.raise_for_status()
            m = r.json()
            if not m.get("closed"):
                return None
            raw = m.get("outcomePrices") or m.get("outcomes")
            if isinstance(raw, str):
                prices = json.loads(raw) if raw.startswith("[") else [raw]
            else:
                prices = raw or []
            if len(prices) >= 2:
                yes_price = float(prices[0]) if isinstance(prices[0], (int, float)) else float(str(prices[0]))
                return yes_price > 0.5
            return None
        except Exception as e:
            logger.warning("Could not fetch market resolution for %s: %s", market_id, e)
            return None

    def poll_until_market(self) -> ActiveMarket:
        """Block until an active market is available."""
        while True:
            m = self.get_active_market()
            if m:
                return m
            logger.info("No active BTC 15m market. Retrying in %ds...", self.POLL_INTERVAL)
            time.sleep(self.POLL_INTERVAL)
