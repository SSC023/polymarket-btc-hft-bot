"""
Live-updating Rich terminal dashboard with P&L sparkline.
"""

import time
from datetime import datetime
from typing import List, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from config import POSITION_SIZE_USD, CIRCUIT_BREAKER_LOSS_USD

# Unicode block characters for ASCII sparkline (low to high)
_SPARK_CHARS = "▁▂▃▄▅▆▇█"
_SPARK_WIDTH = 24  # Max number of points in sparkline


def _pnl_to_sparkline(values: List[float]) -> str:
    """Convert a list of P&L values to a unicode sparkline string."""
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
    """Format time remaining until market end."""
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
    btc_binance: Optional[float],
    poly_implied: Optional[float],
    session_pnl: float,
    usdc_balance: Optional[float],
    pol_balance: Optional[float],
    circuit_breaker: bool,
    pnl_history: Optional[List[float]] = None,
):
    """Build the dashboard panel with live P&L sparkline."""
    status = "[bold red]CIRCUIT BREAKER ACTIVE" if circuit_breaker else "[green]RUNNING"
    title = f"Polymarket BTC 15m HFT Bot — {status}"

    table = Table(show_header=False, box=None)
    table.add_column("Key", style="cyan", width=25)
    table.add_column("Value", style="white")

    table.add_row("Active Market", market_name or "Scanning...")
    table.add_row("Time Left", market_time_left or "—")
    table.add_row("")
    btc_str = f"${btc_binance:,.2f}" if btc_binance is not None else "—"
    poly_str = f"{poly_implied:.2%}" if poly_implied is not None else "—"
    table.add_row("BTC (Binance)", btc_str)
    table.add_row("Yes (Polymarket)", poly_str)
    table.add_row("")
    pnl_style = "red" if session_pnl < 0 else "green"
    table.add_row("Session P&L", Text.from_markup(f"[{pnl_style}]${session_pnl:+.2f}[/]"))
    # P&L sparkline - session trend over time
    sparkline = _pnl_to_sparkline(pnl_history or [])
    table.add_row("P&L Trend", sparkline or "—")
    table.add_row("Daily Circuit Breaker", f"-$ {CIRCUIT_BREAKER_LOSS_USD:.0f}")
    table.add_row("")
    usdc_str = f"${usdc_balance:,.2f}" if usdc_balance is not None else "—"
    pol_str = f"{pol_balance:.4f} POL" if pol_balance is not None else "—"
    table.add_row("Wallet USDC", usdc_str)
    table.add_row("Wallet POL (gas)", pol_str)
    table.add_row("")
    table.add_row("Position Size", f"${POSITION_SIZE_USD:.0f}")

    return Panel(table, title=title, border_style="blue")


def run_dashboard(
    get_state,
    refresh_interval: float = 1.0,
):
    """
    Run live dashboard. get_state() returns dict with keys:
    market_name, market_time_left, btc_binance, poly_implied,
    session_pnl, usdc_balance, pol_balance, circuit_breaker, pnl_history.
    """
    console = Console()

    def render():
        state = get_state()
        return create_dashboard(
            market_name=state.get("market_name", ""),
            market_time_left=state.get("market_time_left", ""),
            btc_binance=state.get("btc_binance"),
            poly_implied=state.get("poly_implied"),
            session_pnl=state.get("session_pnl", 0),
            usdc_balance=state.get("usdc_balance"),
            pol_balance=state.get("pol_balance"),
            circuit_breaker=state.get("circuit_breaker", False),
            pnl_history=state.get("pnl_history", []),
        )

    with Live(render(), console=console, refresh_per_second=2) as live:
        try:
            while True:
                time.sleep(refresh_interval)
                live.update(render())
        except KeyboardInterrupt:
            pass
