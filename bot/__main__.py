"""
bot/__main__.py
───────────────
Entry point.  Run with:

    python -m bot

Sets up logging, builds the Application, registers all handlers,
then starts polling via the local Bot API server.

This bot always runs against a self-hosted Telegram Bot API server.
Set TELEGRAM_LOCAL_SERVER_URL, TELEGRAM_API_ID, and TELEGRAM_API_HASH
in your .env file before starting.
"""

from __future__ import annotations

import logging

from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.config.logging_config import setup_logging
from bot.config.settings import get_settings
from bot.handlers.commands import (
    callback_handler,
    cmd_clearpath,
    cmd_help,
    cmd_setpath,
    cmd_start,
    cmd_status,
)
from bot.handlers.upload import handle_file

logger = logging.getLogger(__name__)


def build_application() -> Application:
    cfg = get_settings()

    base_url = cfg.telegram_local_server_url + "/bot"
    base_file_url = cfg.telegram_local_server_url + "/file/bot"

    logger.info("Connecting to local Bot API server: %s", cfg.telegram_local_server_url)

    app = (
        Application.builder()
        .token(cfg.telegram_bot_token)
        .local_mode(True)
        .base_url(base_url)
        .base_file_url(base_file_url)
        .build()
    )

    # ── Commands ──────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("setpath", cmd_setpath))
    app.add_handler(CommandHandler("clearpath", cmd_clearpath))
    app.add_handler(CommandHandler("status", cmd_status))

    # ── Inline keyboard callbacks ─────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(callback_handler))

    # ── File uploads – catch all supported attachment types ───────────────
    file_filter = (
        filters.Document.ALL
        | filters.PHOTO
        | filters.VIDEO
        | filters.AUDIO
        | filters.VOICE
        | filters.Sticker.ALL
        | filters.VIDEO_NOTE
        | filters.ANIMATION
    )
    app.add_handler(MessageHandler(file_filter, handle_file))

    return app


def main() -> None:
    cfg = get_settings()
    setup_logging(level=cfg.log_level, log_file=cfg.log_file)
    logger.info("Starting bot … %r", cfg)

    app = build_application()
    logger.info("Bot is running. Press Ctrl+C to stop.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
