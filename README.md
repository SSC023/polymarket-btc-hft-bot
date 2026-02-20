# Polymarket Passive Market Making Bot

24/7 liquidity provision bot for Polymarket. Targets markets with **Liquidity Rewards**, places symmetrical Post-Only limit orders on both Yes and No sides.

## Quick Start

```bash
# 1. Copy env template and fill in
cp .env.template .env
# Edit .env: add PRIVATE_KEY (Hot Wallet)

# 2. Install deps
pip install -r requirements.txt

# 3. (Optional) Derive API keys if not in .env
python scripts/setup_api_keys.py

# 4. Run bot
python bot.py
```

## 3 Things You MUST Do Before Trading

### 1. The "Safety" Wallet
**Do NOT use your main MetaMask.** Create a new "Hot Wallet":
- Send **50 USDC** and **5 POL** (for gas) to it on **Polygon**

### 2. API Keys
Go to [Polymarket API Settings](https://polymarket.com) → Settings → API:
- Ensure **"Trading"** is enabled
- Provide API Key, Secret, and Passphrase (or run `scripts/setup_api_keys.py`)

### 3. Market Selection
The bot targets markets with `rewards_min_size > 0`, skips short-term (15-min) markets, and prefers Crypto/Pop Culture tags.

## Architecture

| Module           | Purpose                                           |
|------------------|---------------------------------------------------|
| `config`         | Env vars, constants                               |
| `auth`           | ClobClient, API credential derivation             |
| `scanner`        | Gamma API: liquidity rewards markets, high volume |
| `order_book_feed`| Polymarket Order Book WebSocket                    |
| `strategy`       | Symmetrical quotes: Yes bid at mid-spread, No bid  |
| `execution`      | Order Manager, inventory limits, cancel_all        |
| `dashboard`      | Mid-price, active bids, inventory, P&L sparkline  |
| `analytics`      | CSVLogger → trade_history.csv                      |
| `logger`         | File logging → bot_system.log                      |
| `bot`            | Main orchestration                                 |

## Strategy

- **Quoting**: Mid-price = (best_bid + best_ask) / 2
- **Yes bid**: mid_price - target_spread (default 0.03)
- **No bid**: (1 - mid_price) - target_spread
- **Inventory limit**: Max 50 shares Yes, 50 shares No
- **Re-quote**: When mid drifts > 0.01, cancel_all and re-quote
- **Circuit breaker**: Stop if daily loss > $50

## Files

- `.env.template` – Environment template
- `.gitignore` – Protects `.env`, `*.csv`, `*.log`
- `requirements.txt` – Python dependencies
- `bot.py` – Main entry
- `trade_history.csv` – Trade log (gitignored)
- `bot_system.log` – System events (gitignored)
