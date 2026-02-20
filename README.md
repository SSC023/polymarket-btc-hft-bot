# Polymarket BTC 15-Minute HFT Bot

24/7 high-frequency trading bot for Polymarket's recurring 15-minute BTC Price (Up/Down) markets using latency arbitrage: Binance (lead) → Polymarket (lag).

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
**Do NOT use your main MetaMask.** Create a new "Hot Wallet" for the bot:
- Create a new wallet (MetaMask, or any)
- Send **50 USDC** and **5 POL** (for gas) to it on **Polygon**
- Use only that wallet's private key in `.env`

### 2. API Keys
Go to [Polymarket API Settings](https://polymarket.com) → Settings → API:
- Ensure **"Trading"** is enabled
- Provide API Key, Secret, and Passphrase to the bot
- Or run `python scripts/setup_api_keys.py` to derive from `PRIVATE_KEY`

### 3. Series ID / Slug
If the bot doesn't find the BTC 15m market, Polymarket may have changed the series. Add to `.env`:

```
BTC_15M_SLUG=bitcoin-price-15-minute
```

(You can ask Cursor: "Update the scanner to search by slug 'bitcoin-price-15-minute' instead.")

## Architecture

| Module      | Purpose                                      |
|------------|-----------------------------------------------|
| `config`   | Env vars, constants                           |
| `auth`     | ClobClient, API credential derivation        |
| `scanner`  | Gamma API polling, market discovery, switch   |
| `binance_feed` | Binance WebSocket real-time BTC price (with exponential backoff reconnect) |
| `strategy` | Latency arbitrage: jump >0.1%, EV >1.02     |
| `execution`| Post-only orders, cancel_all, circuit breaker|
| `dashboard`| Rich live terminal UI + P&L sparkline         |
| `analytics`| CSVLogger → trade_history.csv                |
| `logger`   | File logging → bot_system.log                 |
| `bot`      | Main orchestration                           |

## Strategy

- **Lead**: Binance WebSocket BTCUSDT
- **Lag**: Polymarket Yes share price (midpoint)
- **Trigger**: Binance jumps >0.1%, Polymarket stale, EV > 1.02
- **Action**: Post-only limit order (maker rewards, no taker fees)
- **Size**: $10 USDC per trade
- **Circuit breaker**: Stop if daily loss > $50

## Files

- `.env.template` – Environment template
- `.gitignore` – Protects `.env`, `__pycache__/`, `.cursor/`, `*.csv`, `*.log`
- `requirements.txt` – Python dependencies
- `bot.py` – Main entry
- `scripts/setup_api_keys.py` – Derive Polymarket API keys
- `trade_history.csv` – Trade log (gitignored) for pivot tables & analysis
- `bot_system.log` – System events (gitignored) for headless debug
