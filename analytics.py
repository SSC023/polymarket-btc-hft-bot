"""
Analytics and persistent trade logging for post-trade analysis.
CSVLogger appends to trade_history.csv for pivot tables and forecasting.
"""

import csv
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

# Default filename (gitignored)
DEFAULT_CSV_PATH = "trade_history.csv"

CSV_HEADERS = [
    "Timestamp",
    "Market_ID",
    "BTC_Price",
    "Share_Price_Bought",
    "EV_at_Execution",
    "Result",
    "PnL",
    "Cumulative_PnL",
]


class CSVLogger:
    """
    Thread-safe CSV logger for trade events.
    Appends rows on trade execution and market resolution.
    """

    def __init__(self, filepath: Optional[str] = None):
        self._path = Path(filepath or DEFAULT_CSV_PATH)
        self._lock = threading.Lock()
        self._cumulative_pnl: float = 0.0
        self._ensure_header()

    def _ensure_header(self) -> None:
        """Create file with headers if it doesn't exist."""
        with self._lock:
            if not self._path.exists():
                with open(self._path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(CSV_HEADERS)

    def _append_row(self, row: dict) -> None:
        """Append a single row to the CSV."""
        with self._lock:
            with open(self._path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
                writer.writerow({k: row.get(k, "") for k in CSV_HEADERS})

    def log_trade_executed(
        self,
        market_id: str,
        btc_price: float,
        share_price_bought: float,
        ev_at_execution: float,
        size: float,
    ) -> None:
        """
        Log when a trade is executed.
        Result=EXECUTED, PnL=0 (not yet realized).
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        self._append_row({
            "Timestamp": timestamp,
            "Market_ID": str(market_id),
            "BTC_Price": f"{btc_price:.2f}",
            "Share_Price_Bought": f"{share_price_bought:.4f}",
            "EV_at_Execution": f"{ev_at_execution:.4f}",
            "Result": "EXECUTED",
            "PnL": "0.00",
            "Cumulative_PnL": f"{self._cumulative_pnl:.2f}",
        })

    def log_market_resolved(
        self,
        market_id: str,
        btc_price: float,
        share_price_bought: float,
        ev_at_execution: float,
        result_yes_won: Optional[bool],
        size: float,
    ) -> float:
        """
        Log when a 15-minute market resolves.
        Computes PnL: Win = size * (1 - share_price), Loss = -size * share_price.
        result_yes_won: True/False for Win/Loss, None for UNKNOWN (PnL=0).
        Returns the PnL for this position.
        """
        if result_yes_won is True:
            pnl = size * (1.0 - share_price_bought)
            result_str = "Win"
        elif result_yes_won is False:
            pnl = -size * share_price_bought
            result_str = "Loss"
        else:
            pnl = 0.0
            result_str = "UNKNOWN"

        self._cumulative_pnl += pnl
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        self._append_row({
            "Timestamp": timestamp,
            "Market_ID": str(market_id),
            "BTC_Price": f"{btc_price:.2f}",
            "Share_Price_Bought": f"{share_price_bought:.4f}",
            "EV_at_Execution": f"{ev_at_execution:.4f}",
            "Result": result_str,
            "PnL": f"{pnl:.2f}",
            "Cumulative_PnL": f"{self._cumulative_pnl:.2f}",
        })

        return pnl

    @property
    def cumulative_pnl(self) -> float:
        return self._cumulative_pnl

    @property
    def filepath(self) -> Path:
        return self._path
