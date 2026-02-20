#!/usr/bin/env python3
"""
Polymarket Passive Market Making Bot.
24/7 liquidity provision on markets with rewards. Symmetrical quotes around mid_price.
"""

import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional, Set

from rich.console import Console
from rich.live import Live

from config import POSITION_SIZE_USD, CIRCUIT_BREAKER_LOSS_USD
from dashboard import create_dashboard, format_time_left
from order_book_feed import OrderBookFeed
from execution import OrderManager
from auth import create_clob_client
from scanner import Scanner, ActiveMarket
from strategy import MarketMakerStrategy, QuoteSignal

from logger import setup_logging
from analytics import CSVLogger
import logging

try:
    from web3 import Web3
    WEB3_AVAILABLE = True
except ImportError:
    WEB3_AVAILABLE = False

setup_logging()
logger = logging.getLogger(__name__)

POLYGON_RPC = "https://polygon-rpc.com"


@dataclass
class BotState:
    market: Optional[ActiveMarket] = None
    mid_price: Optional[float] = None
    session_pnl: float = 0.0
    usdc_balance: Optional[float] = None
    pol_balance: Optional[float] = None
    circuit_breaker: bool = False
    pnl_history: List[float] = field(default_factory=list)


def fetch_usdc_balance(client) -> Optional[float]:
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
                    if isinstance(v, str) and v.replace(".", "").replace("-", "").replace(".", "", 1).isdigit():
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
    if not WEB3_AVAILABLE or not address:
        return None
    try:
        w3 = Web3(Web3.HTTPProvider(POLYGON_RPC))
        return w3.from_wei(w3.eth.get_balance(address), "ether")
    except Exception:
        return None


def run_bot():
    console = Console()

    try:
        client = create_clob_client()
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    address = client.get_address()
    manager = OrderManager(client)
    scanner = Scanner()
    strategy = MarketMakerStrategy()
    analytics = CSVLogger()

    state = BotState()
    feed: Optional[OrderBookFeed] = None
    last_pnl_sample_time = 0.0
    pnl_sample_interval = 10.0
    last_trade_ids: Set[str] = set()

    def update_balances():
        state.usdc_balance = fetch_usdc_balance(client)
        if address:
            state.pol_balance = fetch_pol_balance(address)

    console.print("[yellow]Canceling any stale orders...[/yellow]")
    manager.cancel_all_orders()
    update_balances()

    # Find initial market
    console.print("[yellow]Scanning for liquidity rewards market...[/yellow]")
    market = scanner.get_active_market()
    if not market:
        console.print("[red]No market with liquidity rewards found.[/red]")
        sys.exit(1)

    state.market = market
    console.print(f"[green]Active market: {market.question}[/green]")

    feed = OrderBookFeed(market.yes_token_id, market.no_token_id)
    feed.start()
    console.print("[green]Order book feed started.[/green]")

    strategy_check_interval = 3.0
    last_strategy_check = 0.0
    dashboard_refresh = 0.5

    def get_dashboard_state():
        yes_bid = manager.active_yes_bid
        no_bid = manager.active_no_bid
        return {
            "market_name": state.market.question if state.market else "",
            "market_time_left": format_time_left(state.market.end_date_iso) if state.market else "",
            "mid_price": state.mid_price,
            "active_yes_bid": yes_bid,
            "active_no_bid": no_bid,
            "inventory_yes": manager.inventory_yes,
            "inventory_no": manager.inventory_no,
            "session_pnl": state.session_pnl,
            "usdc_balance": state.usdc_balance,
            "pol_balance": float(state.pol_balance) if state.pol_balance is not None else None,
            "circuit_breaker": state.circuit_breaker,
            "pnl_history": state.pnl_history,
        }

    def render():
        s = get_dashboard_state()
        return create_dashboard(
            market_name=s["market_name"],
            market_time_left=s["market_time_left"],
            mid_price=s["mid_price"],
            active_yes_bid=s["active_yes_bid"],
            active_no_bid=s["active_no_bid"],
            inventory_yes=s["inventory_yes"],
            inventory_no=s["inventory_no"],
            session_pnl=s["session_pnl"],
            usdc_balance=s["usdc_balance"],
            pol_balance=s["pol_balance"],
            circuit_breaker=s["circuit_breaker"],
            pnl_history=s["pnl_history"],
        )

    try:
        with Live(render(), console=console, refresh_per_second=2) as live:
            while True:
                time.sleep(dashboard_refresh)
                now = time.monotonic()

                if manager.circuit_breaker_tripped:
                    state.circuit_breaker = True
                    live.update(render())
                    console.print("[bold red]CIRCUIT BREAKER: Bot stopped.[/bold red]")
                    break

                state.mid_price = feed.mid_price
                state.session_pnl = manager.session_pnl

                if now - last_pnl_sample_time >= pnl_sample_interval:
                    last_pnl_sample_time = now
                    state.pnl_history.append(state.session_pnl)
                    if len(state.pnl_history) > 48:
                        state.pnl_history = state.pnl_history[-48:]

                # Re-scan market periodically (in case we need to switch)
                if int(now) % 60 < 2:
                    m = scanner.get_active_market()
                    if m and m.market_id != (state.market.market_id if state.market else ""):
                        state.market = m
                        manager.cancel_all_orders()
                        if feed:
                            feed.stop()
                        feed = OrderBookFeed(m.yes_token_id, m.no_token_id)
                        feed.start()
                        logger.info("Switched to market: %s", m.question)

                # Mid-price drift: cancel and re-quote
                if state.mid_price is not None and manager.should_requote(state.mid_price):
                    manager.cancel_all_orders()
                    manager.set_last_mid(state.mid_price)
                    logger.info("Mid drifted, re-quoting at %.3f", state.mid_price)

                # Strategy: place symmetrical quotes
                if now - last_strategy_check >= strategy_check_interval and state.market:
                    last_strategy_check = now
                    if (
                        state.mid_price
                        and state.market.accepting_orders
                        and not state.circuit_breaker
                    ):
                        manager.set_last_mid(state.mid_price)
                        size = round(POSITION_SIZE_USD / max(state.mid_price, 0.1), 2)
                        quotes = strategy.get_quotes(
                            state.mid_price,
                            state.market.yes_token_id,
                            state.market.no_token_id,
                            size=min(size, 20),
                            quote_yes=manager.can_quote_yes(),
                            quote_no=manager.can_quote_no(),
                        )
                        for q in quotes:
                            placed = manager.place_post_only_limit_order(
                                token_id=q.token_id,
                                side=q.side,
                                price=q.price,
                                size=q.size,
                                outcome=q.outcome,
                            )
                            if placed:
                                analytics.log_order_placed(
                                    state.market.market_id,
                                    q.outcome,
                                    q.price,
                                    q.size,
                                )

                # Poll for fills (best-effort)
                if int(now) % 30 == 0 and state.market:
                    try:
                        trades = client.get_trades()
                        for t in (trades or [])[:20]:
                            tid = t.get("id") or t.get("trade_id") or str(t)
                            if tid and tid not in last_trade_ids:
                                last_trade_ids.add(tid)
                                if len(last_trade_ids) > 500:
                                    last_trade_ids.clear()
                                aid = str(t.get("asset_id") or t.get("token_id") or "")
                                outcome = "Yes" if aid == state.market.yes_token_id else "No"
                                price = float(t.get("price", 0) or 0)
                                size = float(t.get("size", t.get("amount", 0)) or 0)
                                if price > 0 and size > 0:
                                    analytics.log_passive_fill(state.market.market_id, outcome, price, size)
                                    manager.record_fill(outcome, size, price)
                    except Exception as e:
                        logger.debug("Trade poll: %s", e)

                if int(now) % 30 < 1:
                    update_balances()

                live.update(render())

    except KeyboardInterrupt:
        console.print("\n[yellow]Shutting down...[/yellow]")
    finally:
        if feed:
            feed.stop()
        manager.cancel_all_orders()


if __name__ == "__main__":
    run_bot()
