#!/usr/bin/env python3
"""
Polymarket BTC 15-Minute HFT Bot.
24/7 latency arbitrage: Binance lead → Polymarket lag.
"""

import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from rich.console import Console
from rich.live import Live

from binance_feed import BinancePriceFeed
from config import POSITION_SIZE_USD, CIRCUIT_BREAKER_LOSS_USD
from dashboard import create_dashboard, format_time_left
from execution import ExecutionEngine
from auth import create_clob_client
from scanner import Scanner, ActiveMarket
from strategy import LatencyArbitrageStrategy, TradeSignal

from logger import setup_logging
from analytics import CSVLogger
import logging

# Optional: web3 for POL balance
try:
    from web3 import Web3
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False

# Configure logging (file + console) - must run before other imports use logging
setup_logging()
logger = logging.getLogger(__name__)

# Polygon RPC for balance checks
POLYGON_RPC = "https://polygon-rpc.com"


@dataclass
class BotState:
    """Shared state for dashboard and strategy."""

    market: Optional[ActiveMarket] = None
    btc_price: Optional[float] = None
    poly_yes_price: Optional[float] = None
    session_pnl: float = 0.0
    usdc_balance: Optional[float] = None
    pol_balance: Optional[float] = None
    circuit_breaker: bool = False
    pnl_history: List[float] = field(default_factory=list)


def fetch_usdc_balance(client) -> Optional[float]:
    """Get USDC balance from CLOB."""
    try:
        from py_clob_client.clob_types import BalanceAllowanceParams, AssetType
        params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
        resp = client.get_balance_allowance(params)
        if resp and isinstance(resp, dict):
            for key in ("balance", "allowance", "balanceAllowance", "available"):
                if key in resp:
                    v = resp[key]
                    if isinstance(v, (int, float)):
                        return float(v)
                    if isinstance(v, str) and v.replace(".", "").isdigit():
                        return float(v)
            if "balances" in resp:
                for b in resp["balances"]:
                    if isinstance(b, dict) and b.get("currency", "").upper() in ("USD", "USDC"):
                        return float(b.get("currentBalance", b.get("balance", 0)) or 0)
        return None
    except Exception as e:
        logger.debug("Balance fetch failed: %s", e)
        return None


def fetch_pol_balance(address: str) -> Optional[float]:
    """Get native POL balance on Polygon."""
    if not WEB3_AVAILABLE or not address:
        return None
    try:
        w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
        balance_wei = w3.eth.get_balance(address)
        return w3.from_wei(balance_wei, "ether")
    except Exception as e:
        logger.debug("POL balance fetch failed: %s", e)
        return None


def run_bot():
    """Main bot loop with dashboard."""
    console = Console()

    # Auth
    try:
        client = create_clob_client()
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    address = client.get_address()
    engine = ExecutionEngine(client)
    scanner = Scanner()
    strategy = LatencyArbitrageStrategy()
    feed = BinancePriceFeed()
    analytics = CSVLogger()

    state = BotState()
    # Pending positions per market: market_id -> [(share_price, size, ev), ...]
    pending_positions: Dict[str, List[Tuple[float, float, float]]] = defaultdict(list)
    last_pnl_sample_time = 0.0
    pnl_sample_interval = 10.0  # seconds between sparkline samples

    def update_balances():
        state.usdc_balance = fetch_usdc_balance(client)
        if address:
            state.pol_balance = fetch_pol_balance(address)

    # Cancel stale orders before starting
    console.print("[yellow]Canceling any stale orders...[/yellow]")
    engine.cancel_all_orders()
    update_balances()

    # Start Binance feed
    feed.start()
    console.print("[green]Binance price feed started.[/green]")

    # Find initial market
    console.print("[yellow]Scanning for BTC 15m market...[/yellow]")
    market = scanner.get_active_market()
    if not market:
        console.print(
            "[red]No active BTC 15-minute market found. "
            "If Polymarket changed the series, set BTC_15M_SLUG in .env (e.g. bitcoin-price-15-minute)[/red]"
        )
        feed.stop()
        sys.exit(1)

    state.market = market
    console.print(f"[green]Active market: {market.question}[/green]")

    last_market_id = market.market_id
    strategy_check_interval = 2.0
    last_strategy_check = 0.0
    dashboard_refresh = 0.5

    def get_dashboard_state():
        return {
            "market_name": state.market.question if state.market else "",
            "market_time_left": format_time_left(state.market.end_date_iso) if state.market else "",
            "btc_binance": state.btc_price,
            "poly_implied": state.poly_yes_price,
            "session_pnl": state.session_pnl,
            "usdc_balance": state.usdc_balance,
            "pol_balance": float(state.pol_balance) if state.pol_balance is not None else None,
            "circuit_breaker": state.circuit_breaker,
            "pnl_history": state.pnl_history,
        }

    def render():
        return create_dashboard(**get_dashboard_state())

    try:
        with Live(render(), console=console, refresh_per_second=2) as live:
            while True:
                time.sleep(dashboard_refresh)
                now = time.monotonic()

                # Circuit breaker
                if engine.circuit_breaker_tripped:
                    state.circuit_breaker = True
                    live.update(render())
                    console.print("[bold red]CIRCUIT BREAKER: Bot stopped. Daily loss limit reached.[/bold red]")
                    break

                # Update prices
                state.btc_price = feed.price
                state.session_pnl = engine.session_pnl

                # Sample P&L for sparkline (throttled)
                if now - last_pnl_sample_time >= pnl_sample_interval:
                    last_pnl_sample_time = now
                    state.pnl_history.append(state.session_pnl)
                    if len(state.pnl_history) > 48:
                        state.pnl_history = state.pnl_history[-48:]

                # Market switch: has current market ended?
                market = scanner.get_active_market()
                if market and market.market_id != last_market_id:
                    # Resolve previous market and log P&L
                    if last_market_id and last_market_id in pending_positions:
                        resolution = scanner.get_market_resolution(last_market_id)
                        btc_at_resolve = state.btc_price or 0
                        for share_price, size, ev in pending_positions[last_market_id]:
                            pnl = analytics.log_market_resolved(
                                market_id=last_market_id,
                                btc_price=btc_at_resolve,
                                share_price_bought=share_price,
                                ev_at_execution=ev,
                                result_yes_won=resolution,
                                size=size,
                            )
                            engine.record_pnl(pnl)
                        pending_positions.pop(last_market_id, None)
                        logger.info("Market %s resolved, logged to trade_history.csv", last_market_id)

                    last_market_id = market.market_id
                    state.market = market
                    engine.cancel_all_orders()
                    logger.info("Switched to new market: %s", market.question)

                state.market = market or state.market

                # Fetch Polymarket Yes price
                if state.market and state.market.accepting_orders:
                    try:
                        mid = client.get_midpoint(state.market.yes_token_id)
                        state.poly_yes_price = float(mid) if mid is not None else None
                    except Exception:
                        state.poly_yes_price = None

                # Strategy check (throttled)
                if now - last_strategy_check >= strategy_check_interval and state.market:
                    last_strategy_check = now
                    if (
                        state.btc_price
                        and state.poly_yes_price
                        and state.market.accepting_orders
                        and not state.circuit_breaker
                    ):
                        signal = strategy.check_signal(
                            yes_token_id=state.market.yes_token_id,
                            binance_price=state.btc_price,
                            binance_prev_price=feed.prev_price,
                            binance_change_pct=feed.price_change_pct(),
                            poly_yes_price=state.poly_yes_price,
                            position_size_usd=POSITION_SIZE_USD,
                        )
                        if signal:
                            placed = engine.place_post_only_limit_order(
                                token_id=signal.token_id,
                                side=signal.side,
                                price=signal.price,
                                size=signal.size,
                            )
                            if placed:
                                analytics.log_trade_executed(
                                    market_id=state.market.market_id,
                                    btc_price=state.btc_price,
                                    share_price_bought=signal.price,
                                    ev_at_execution=signal.ev,
                                    size=signal.size,
                                )
                                pending_positions[state.market.market_id].append(
                                    (signal.price, signal.size, signal.ev)
                                )
                                logger.info("Order placed: %s @ %.3f x %.2f (EV=%.3f)", signal.side, signal.price, signal.size, signal.ev)

                # Periodic balance update
                if int(now) % 30 < 1:
                    update_balances()

                live.update(render())

    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
    finally:
        feed.stop()
        engine.cancel_all_orders()


if __name__ == "__main__":
    run_bot()
