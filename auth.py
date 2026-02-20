"""
Authentication and ClobClient setup for Polymarket.
Supports derived API credentials or pre-configured Key/Secret/Passphrase.
"""

import os
from typing import Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds

from config import (
    PRIVATE_KEY,
    POLYMARKET_API_KEY,
    POLYMARKET_API_SECRET,
    POLYMARKET_API_PASSPHRASE,
    CHAIN_ID,
    CLOB_HOST,
)


def create_api_creds() -> Optional[ApiCreds]:
    """Create or derive API credentials from private key if not provided."""
    if POLYMARKET_API_KEY and POLYMARKET_API_SECRET and POLYMARKET_API_PASSPHRASE:
        return ApiCreds(
            api_key=POLYMARKET_API_KEY,
            api_secret=POLYMARKET_API_SECRET,
            api_passphrase=POLYMARKET_API_PASSPHRASE,
        )
    if not PRIVATE_KEY:
        return None
    try:
        temp_client = ClobClient(CLOB_HOST, chain_id=CHAIN_ID, key=PRIVATE_KEY)
        creds = temp_client.create_or_derive_api_creds()
        return creds
    except Exception as e:
        raise RuntimeError(f"Failed to create/derive API credentials: {e}") from e


def create_clob_client() -> ClobClient:
    """
    Create a fully authenticated ClobClient.
    Derives API credentials from private key if not in env.
    """
    if not PRIVATE_KEY:
        raise ValueError(
            "PRIVATE_KEY is required. Use a dedicated Hot Wallet (see .env.template)."
        )
    creds = create_api_creds()
    if not creds:
        raise ValueError(
            "Could not obtain API credentials. Set POLYMARKET_API_KEY, SECRET, PASSPHRASE "
            "or run scripts/setup_api_keys.py to derive from PRIVATE_KEY."
        )
    client = ClobClient(
        CLOB_HOST,
        chain_id=CHAIN_ID,
        key=PRIVATE_KEY,
        creds=creds,
    )
    return client
