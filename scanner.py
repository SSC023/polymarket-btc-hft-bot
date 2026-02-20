"""
24/7 Market Discovery - Gamma API Scanner for Liquidity Rewards markets.
Targets high-volume, longer-term markets (Crypto, Pop Culture) with rewards_min_size > 0.
Skips short-term 15-minute markets.
"""

import json
import logging
from dataclasses import dataclass
from typing import Optional

import requests

from config import GAMMA_EVENTS_URL, GAMMA_API_URL

logger = logging.getLogger(__name__)

# Preferred tags for market making (high volume, longer-term)
PREFERRED_TAG_SLUGS = frozenset({"crypto", "bitcoin", "ethereum", "pop-culture", "entertainment", "sports"})

# Title patterns to EXCLUDE (short-term markets)
EXCLUDE_PATTERNS = ("15-minute", "15 minute", "5-minute", "1-hour", "1 hour", "hourly")


@dataclass
class ActiveMarket:
    """Represents a market with liquidity rewards."""

    event_id: str
    event_slug: str
    market_id: str
    question: str
    end_date_iso: str
    yes_token_id: str
    no_token_id: str
    accepting_orders: bool
    rewards_min_size: int


class Scanner:
    """
    Polls Gamma API for markets with liquidity rewards.
    Filters: rewards_min_size > 0, active, skip short-term, prefer Crypto/Pop Culture.
    """

    POLL_INTERVAL = 60  # seconds
    REQUEST_TIMEOUT = 15

    def __init__(self):
        self._last_market: Optional[ActiveMarket] = None

    def _fetch_events(self, limit: int = 100, order: str = "volume_24hr") -> list:
        """Fetch active events from Gamma API, sorted by volume."""
        params = {
            "active": "true",
            "closed": "false",
            "limit": limit,
            "order": order,
            "ascending": "false",
        }
        try:
            r = requests.get(GAMMA_EVENTS_URL, params=params, timeout=self.REQUEST_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            return data if isinstance(data, list) else []
        except requests.RequestException as e:
            logger.warning("Gamma API request failed: %s", e)
            return []

    def _parse_clob_token_ids(self, raw: str) -> tuple[str, str]:
        """Parse clobTokenIds JSON string. Returns (yes_token_id, no_token_id)."""
        try:
            ids = json.loads(raw)
            if isinstance(ids, list) and len(ids) >= 2:
                return str(ids[0]), str(ids[1])
        except (json.JSONDecodeError, TypeError):
            pass
        return "", ""

    def _is_short_term(self, event: dict, market: dict) -> bool:
        """Return True if market is short-term (15-min, hourly, etc.)."""
        title = (event.get("title") or "").lower()
        question = (market.get("question") or "").lower()
        combined = f"{title} {question}"
        return any(p in combined for p in EXCLUDE_PATTERNS)

    def _has_preferred_tag(self, event: dict) -> bool:
        """Check if event has a preferred tag (Crypto, Pop Culture, etc.)."""
        tags = event.get("tags") or []
        for t in tags:
            slug = (t.get("slug") or "").lower()
            if slug in PREFERRED_TAG_SLUGS:
                return True
        return False

    def _score_market(self, event: dict, market: dict) -> float:
        """Higher score = better candidate. Prefer volume, preferred tags."""
        score = 0.0
        score += float(market.get("volume24hr") or market.get("volumeNum") or 0) / 1e6
        score += float(event.get("volume24hr") or event.get("volume") or 0) / 1e6
        if self._has_preferred_tag(event):
            score += 10.0
        return score

    def get_active_market(self) -> Optional[ActiveMarket]:
        """
        Get the best market with liquidity rewards.
        Filters: rewards_min_size > 0, accepting orders, not short-term.
        """
        events = self._fetch_events(limit=150)
        best: Optional[tuple[float, dict, dict]] = None

        for event in events:
            if not event.get("active") or event.get("closed"):
                continue
            markets = event.get("markets") or []
            for m in markets:
                rewards_min = m.get("rewardsMinSize") or 0
                try:
                    rewards_min = int(rewards_min)
                except (ValueError, TypeError):
                    rewards_min = 0
                if rewards_min <= 0:
                    continue
                if m.get("closed") or not m.get("acceptingOrders", True):
                    continue
                if self._is_short_term(event, m):
                    continue
                yes_id, no_id = self._parse_clob_token_ids(m.get("clobTokenIds") or "[]")
                if not yes_id or not no_id:
                    continue

                score = self._score_market(event, m)
                if best is None or score > best[0]:
                    best = (score, event, m)

        if best is None:
            return None

        _, event, m = best
        yes_id, no_id = self._parse_clob_token_ids(m.get("clobTokenIds") or "[]")
        rewards_min = int(m.get("rewardsMinSize") or 0)

        market = ActiveMarket(
            event_id=str(event.get("id", "")),
            event_slug=str(event.get("slug", "")),
            market_id=str(m.get("id", "")),
            question=str(m.get("question", "")),
            end_date_iso=str(m.get("endDate") or m.get("endDateIso") or ""),
            yes_token_id=yes_id,
            no_token_id=no_id,
            accepting_orders=bool(m.get("acceptingOrders", True)),
            rewards_min_size=rewards_min,
        )
        self._last_market = market
        return market

    def get_market_resolution(self, market_id: str) -> Optional[bool]:
        """Fetch resolved market from Gamma API. Returns True if Yes won, False if No won."""
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
