"""
bot/__main__.py
───────────────
Entry point.  Run with:

    python -m bot

Uses Pyrogram (MTProto) to connect directly to Telegram's servers —
no local Bot API server required.  File size limit is 2 GB natively.
"""

from __future__ import annotations

import logging

from pyrogram import Client, filters

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


def build_client() -> Client:
    cfg = get_settings()
    return Client(
        name="github_uploader_bot",
        api_id=cfg.telegram_api_id,
        api_hash=cfg.telegram_api_hash,
        bot_token=cfg.telegram_bot_token,
    )


def register_handlers(app: Client) -> None:
    # ── Commands ──────────────────────────────────────────────────────────
    app.on_message(filters.command("start") & filters.private)(cmd_start)
    app.on_message(filters.command("help") & filters.private)(cmd_help)
    app.on_message(filters.command("setpath") & filters.private)(cmd_setpath)
    app.on_message(filters.command("clearpath") & filters.private)(cmd_clearpath)
    app.on_message(filters.command("status") & filters.private)(cmd_status)

    # ── Inline keyboard callbacks ─────────────────────────────────────────
    app.on_callback_query()(callback_handler)

    # ── File uploads — catch all supported media types ────────────────────
    file_filter = (
        filters.document
        | filters.photo
        | filters.video
        | filters.audio
        | filters.voice
        | filters.sticker
        | filters.video_note
        | filters.animation
    )
    app.on_message(file_filter & filters.private)(handle_file)


def main() -> None:
    cfg = get_settings()
    setup_logging(level=cfg.log_level, log_file=cfg.log_file)
    logger.info("Starting bot ... %r", cfg)

    app = build_client()
    register_handlers(app)

    logger.info("Bot is running via MTProto (Pyrogram). Press Ctrl+C to stop.")
    app.run()


if __name__ == "__main__":
    main()
