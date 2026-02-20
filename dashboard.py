"""
Live-updating Rich terminal dashboard for Market Making bot.
"""

import time
from datetime import datetime
from typing import List, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import TARGET_SPREAD, CIRCUIT_BREAKER_LOSS_USD

_SPARK_CHARS = "▁▂▃▄▅▆▇█"
_SPARK_WIDTH = 24


def _pnl_to_sparkline(values: List[float]) -> str:
    if not values:
        return "—"
    vmin = min(values)
    vmax = max(values)
    span = vmax - vmin if vmax != vmin else 1.0
    chars = []
    for v in values[-_SPARK_WIDTH:]:
        idx = int((v - vmin) / span * (len(_SPARK_CHARS) - 1))
        idx = max(0, min(idx, len(_SPARK_CHARS) - 1))
        chars.append(_SPARK_CHARS[idx])
    return "".join(chars)


def format_time_left(end_iso: str) -> str:
    if not end_iso:
        return "N/A"
    try:
        s = end_iso.replace("Z", "+00:00")
        end = datetime.fromisoformat(s)
        if end.tzinfo:
            end = end.replace(tzinfo=None)
        now = datetime.utcnow()
    except Exception:
        return end_iso
    delta = end - now
    if delta.total_seconds() <= 0:
        return "Ended"
    s = int(delta.total_seconds())
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s"


def create_dashboard(
    market_name: str,
    market_time_left: str,
    mid_price: Optional[float],
    active_yes_bid: Optional[tuple],
    active_no_bid: Optional[tuple],
    inventory_yes: float,
    inventory_no: float,
    session_pnl: float,
    usdc_balance: Optional[float],
    pol_balance: Optional[float],
    circuit_breaker: bool,
    pnl_history: Optional[List[float]] = None,
):
    """Build the dashboard panel."""
    status = "[bold red]CIRCUIT BREAKER ACTIVE" if circuit_breaker else "[green]RUNNING"
    title = f"Polymarket Market Making Bot — {status}"

    table = Table(show_header=False, box=None)
    table.add_column("Key", style="cyan", width=25)
    table.add_column("Value", style="white")

    table.add_row("Active Market", market_name or "Scanning...")
    table.add_row("Time Left", market_time_left or "—")
    table.add_row("")
    mid_str = f"{mid_price:.3f}" if mid_price is not None else "—"
    table.add_row("Current Mid-Price", mid_str)
    yes_bid_str = f"{active_yes_bid[0]:.3f} x {active_yes_bid[1]:.2f}" if active_yes_bid else "—"
    no_bid_str = f"{active_no_bid[0]:.3f} x {active_no_bid[1]:.2f}" if active_no_bid else "—"
    table.add_row("Active Yes Bid", yes_bid_str)
    table.add_row("Active No Bid", no_bid_str)
    table.add_row("")
    table.add_row("Current Inventory (Yes)", f"{inventory_yes:.1f} shares")
    table.add_row("Current Inventory (No)", f"{inventory_no:.1f} shares")
    table.add_row("")
    pnl_style = "red" if session_pnl < 0 else "green"
    table.add_row("Session P&L", Text.from_markup(f"[{pnl_style}]${session_pnl:+.2f}[/]"))
    sparkline = _pnl_to_sparkline(pnl_history or [])
    table.add_row("P&L Trend", sparkline or "—")
    table.add_row("Target Spread", f"{TARGET_SPREAD:.2f}")
    table.add_row("Daily Circuit Breaker", f"-$ {CIRCUIT_BREAKER_LOSS_USD:.0f}")
    table.add_row("")
    usdc_str = f"${usdc_balance:,.2f}" if usdc_balance is not None else "—"
    pol_str = f"{pol_balance:.4f} POL" if pol_balance is not None else "—"
    table.add_row("Wallet USDC", usdc_str)
    table.add_row("Wallet POL (gas)", pol_str)

    return Panel(table, title=title, border_style="blue")
