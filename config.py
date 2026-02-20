"""
Configuration for Polymarket BTC 15-minute HFT Bot.
Loads from .env with sensible defaults.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Chain
CHAIN_ID = int(os.getenv("CHAIN_ID", "137"))

# Credentials
PRIVATE_KEY = os.getenv("PRIVATE_KEY", "").strip()
POLYMARKET_API_KEY = os.getenv("POLYMARKET_API_KEY", "").strip()
POLYMARKET_API_SECRET = os.getenv("POLYMARKET_API_SECRET", "").strip()
POLYMARKET_API_PASSPHRASE = os.getenv("POLYMARKET_API_PASSPHRASE", "").strip()

# Risk
POSITION_SIZE_USD = float(os.getenv("POSITION_SIZE_USD", "10"))
CIRCUIT_BREAKER_LOSS_USD = float(os.getenv("CIRCUIT_BREAKER_LOSS_USD", "50"))
BINANCE_JUMP_THRESHOLD_PCT = float(os.getenv("BINANCE_JUMP_THRESHOLD_PCT", "0.1"))
EV_THRESHOLD = float(os.getenv("EV_THRESHOLD", "1.02"))

# API URLs
CLOB_HOST = "https://clob.polymarket.com"
GAMMA_API_URL = "https://gamma-api.polymarket.com"
GAMMA_EVENTS_URL = f"{GAMMA_API_URL}/events"

# Market discovery - search by tag 'Bitcoin' + '15-minute' in title, or by slug
# Fallback slug if Gamma API structure changes (see user note in requirements)
BTC_15M_SLUG = os.getenv("BTC_15M_SLUG", "bitcoin-price-15-minute")
