#!/usr/bin/env python3
"""
Setup Polymarket API credentials.
If POLYMARKET_API_KEY/SECRET/PASSPHRASE are not in .env, derives them from PRIVATE_KEY
and prints them for you to add to .env.
"""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from py_clob_client.client import ClobClient

CLOB_HOST = "https://clob.polymarket.com"
CHAIN_ID = 137


def main():
    pk = os.getenv("PRIVATE_KEY", "").strip()
    if not pk:
        print("ERROR: PRIVATE_KEY not set in .env")
        print("Add your Hot Wallet private key to .env and run again.")
        sys.exit(1)

    if os.getenv("POLYMARKET_API_KEY") and os.getenv("POLYMARKET_API_SECRET"):
        print("API credentials already in .env. Nothing to do.")
        sys.exit(0)

    print("Deriving API credentials from PRIVATE_KEY...")
    client = ClobClient(CLOB_HOST, chain_id=CHAIN_ID, key=pk)
    creds = client.create_or_derive_api_creds()
    if not creds:
        print("ERROR: Failed to derive credentials.")
        sys.exit(1)

    print("\n=== Add these to your .env file ===\n")
    print(f"POLYMARKET_API_KEY={creds.api_key}")
    print(f"POLYMARKET_API_SECRET={creds.api_secret}")
    print(f"POLYMARKET_API_PASSPHRASE={creds.api_passphrase}")
    print("\nAlso ensure 'Trading' is enabled in Polymarket API Settings.")
    print("https://polymarket.com → Settings → API")


if __name__ == "__main__":
    main()
