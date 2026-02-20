"""
Application logging for headless server runs.
Writes system events to bot_system.log, separate from terminal UI.
"""

import logging
import os
import sys
from pathlib import Path

LOG_FILE = "bot_system.log"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    *,
    log_file: str = LOG_FILE,
    console_level: int = logging.INFO,
    file_level: int = logging.DEBUG,
) -> None:
    """
    Configure Python logging:
    - Console: INFO (terminal output)
    - File: DEBUG (full system events for headless debugging)
    """
    root = logging.getLogger()
    if root.handlers:
        return

    root.setLevel(min(console_level, file_level))

    # File handler (persistent, for headless debug)
    log_path = Path(log_file)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(file_level)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(file_handler)

    # Console handler (terminal UI)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    """Get a named logger (use __name__ from each module)."""
    return logging.getLogger(name)
