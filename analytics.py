"""
Analytics and persistent trade logging for post-trade analysis.
CSVLogger appends to trade_history.csv for pivot tables and forecasting.
Logs passive limit order fills (market making).
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
    "Outcome",
    "Share_Price_Bought",
    "Size",
    "Order_Type",
    "Result",
    "PnL",
    "Cumulative_PnL",
]


class CSVLogger:
    """
    Thread-safe CSV logger for trade events.
    Logs passive limit order fills. Market resolution PnL tracked separately.
    """

    def __init__(self, filepath: Optional[str] = None):
        self._path = Path(filepath or DEFAULT_CSV_PATH)
        self._lock = threading.Lock()
        self._cumulative_pnl: float = 0.0
        self._ensure_header()

    def _ensure_header(self) -> None:
        with self._lock:
            if not self._path.exists():
                with open(self._path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(CSV_HEADERS)

    def _append_row(self, row: dict) -> None:
        with self._lock:
            with open(self._path, "a", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
                writer.writerow({k: row.get(k, "") for k in CSV_HEADERS})

    def log_order_placed(
        self,
        market_id: str,
        outcome: str,
        share_price: float,
        size: float,
    ) -> None:
        """Log when a passive limit order is placed (pre-fill)."""
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        self._append_row({
            "Timestamp": timestamp,
            "Market_ID": str(market_id),
            "Outcome": outcome,
            "Share_Price_Bought": f"{share_price:.4f}",
            "Size": f"{size:.2f}",
            "Order_Type": "PASSIVE_MM",
            "Result": "PLACED",
            "PnL": "0.00",
            "Cumulative_PnL": f"{self._cumulative_pnl:.2f}",
        })

    def log_passive_fill(
        self,
        market_id: str,
        outcome: str,
        share_price: float,
        size: float,
    ) -> None:
        """
        Log when a passive limit order is filled (market making).
        """
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        self._append_row({
            "Timestamp": timestamp,
            "Market_ID": str(market_id),
            "Outcome": outcome,
            "Share_Price_Bought": f"{share_price:.4f}",
            "Size": f"{size:.2f}",
            "Order_Type": "PASSIVE_MM",
            "Result": "FILLED",
            "PnL": "0.00",
            "Cumulative_PnL": f"{self._cumulative_pnl:.2f}",
        })

    def log_market_resolved(
        self,
        market_id: str,
        share_price_bought: float,
        result_yes_won: Optional[bool],
        size: float,
    ) -> float:
        """
        Log when a market resolves. Computes PnL for Yes position.
        Returns the PnL.
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
            "Outcome": "Yes",
            "Share_Price_Bought": f"{share_price_bought:.4f}",
            "Size": f"{size:.2f}",
            "Order_Type": "PASSIVE_MM",
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
