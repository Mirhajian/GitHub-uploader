"""
bot/config/logging_config.py
─────────────────────────────
Sets up the root logger with both a rotating file handler and a
colourised console handler.  Call `setup_logging()` once at startup.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

_CONSOLE_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_FILE_FMT = "%(asctime)s | %(levelname)-8s | %(name)s | %(funcName)s:%(lineno)d | %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: str = "INFO", log_file: str = "logs/bot.log") -> None:
    """
    Configure root logger.

    Args:
        level:    Log level string, e.g. "DEBUG", "INFO", "WARNING".
        log_file: Path for the rotating log file.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    # Ensure log directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # ── Console handler ───────────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(logging.Formatter(_CONSOLE_FMT, datefmt=_DATE_FMT))

    # ── Rotating file handler (10 MB × 5 backups) ─────────────────────────
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(logging.Formatter(_FILE_FMT, datefmt=_DATE_FMT))

    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Quiet noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)
