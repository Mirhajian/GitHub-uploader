"""
bot/config/logging_config.py
─────────────────────────────
Configures the root logger with:
  • A rotating file handler  (10 MB × 5 backups)
  • A coloured stream handler for the console
"""

from __future__ import annotations

import logging
import logging.handlers
import os


def setup_logging(level: str = "INFO", log_file: str = "logs/bot.log") -> None:
    """
    Call once at startup.  Subsequent calls are no-ops (root logger already
    has handlers after the first call).
    """
    root = logging.getLogger()
    if root.handlers:
        return  # already configured

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root.setLevel(numeric_level)

    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Console handler ───────────────────────────────────────────────────
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    root.addHandler(stream_handler)

    # ── Rotating file handler ─────────────────────────────────────────────
    log_dir = os.path.dirname(log_file)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    # Silence overly verbose third-party loggers
    logging.getLogger("pyrogram").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
