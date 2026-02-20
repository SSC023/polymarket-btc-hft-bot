"""
Configuration for Polymarket Passive Market Making Bot.
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
MAX_INVENTORY_YES = int(os.getenv("MAX_INVENTORY_YES", "50"))
MAX_INVENTORY_NO = int(os.getenv("MAX_INVENTORY_NO", "50"))
MID_PRICE_DRIFT_THRESHOLD = float(os.getenv("MID_PRICE_DRIFT_THRESHOLD", "0.01"))

# Market making
TARGET_SPREAD = float(os.getenv("TARGET_SPREAD", "0.03"))

# API URLs
CLOB_HOST = "https://clob.polymarket.com"
GAMMA_API_URL = "https://gamma-api.polymarket.com"
GAMMA_EVENTS_URL = f"{GAMMA_API_URL}/events"
POLYMARKET_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
