"""
bot/services/file_service.py
─────────────────────────────
Helpers for resolving the largest available Telegram file object,
extracting a meaningful filename, and downloading the raw bytes.

Telegram file-size tiers
──────────────────────────
• Official Bot API  → max 20 MB download / 50 MB upload (bots)
• Local Bot API     → up to 2 000 MB (2 GB)

We always download via `telegram.File.download_as_bytearray()` which
streams in chunks internally.  For very large files (> WARN_MB) we log
a progress note.
"""

from __future__ import annotations

import logging
import mimetypes
from typing import Any

from telegram import (
    Animation,
    Audio,
    Document,
    Message,
    PhotoSize,
    Sticker,
    Video,
    VideoNote,
    Voice,
)

logger = logging.getLogger(__name__)

WARN_MB = 50  # Log a notice for files larger than this


# ── Public helpers ─────────────────────────────────────────────────────────────


async def extract_file_info(message: Message) -> tuple[Any, str]:
    """
    Return *(file_object, filename)* for the first recognised attachment
    in *message*.  Raises ValueError if no supported attachment is found.

    Priority order mirrors Telegram's multipart update structure so that
    documents (which preserve original filenames) are preferred over
    generic photo thumbnails.
    """
    # Document  ──────────────────────────────────────────────────────────
    if message.document:
        doc: Document = message.document
        filename = doc.file_name or f"document_{doc.file_unique_id}"
        return doc, filename

    # Photo ──────────────────────────────────────────────────────────────
    if message.photo:
        best: PhotoSize = message.photo[-1]  # last = highest resolution
        filename = f"photo_{best.file_unique_id}.jpg"
        return best, filename

    # Video ──────────────────────────────────────────────────────────────
    if message.video:
        vid: Video = message.video
        filename = vid.file_name or f"video_{vid.file_unique_id}{_ext(vid.mime_type, '.mp4')}"
        return vid, filename

    # Audio ──────────────────────────────────────────────────────────────
    if message.audio:
        aud: Audio = message.audio
        if aud.file_name:
            filename = aud.file_name
        elif aud.title:
            filename = f"{aud.title}{_ext(aud.mime_type, '.mp3')}"
        else:
            filename = f"audio_{aud.file_unique_id}{_ext(aud.mime_type, '.mp3')}"
        return aud, filename

    # Voice ──────────────────────────────────────────────────────────────
    if message.voice:
        voice: Voice = message.voice
        filename = f"voice_{voice.file_unique_id}{_ext(voice.mime_type, '.ogg')}"
        return voice, filename

    # Animation (GIF) ────────────────────────────────────────────────────
    if message.animation:
        anim: Animation = message.animation
        filename = anim.file_name or f"animation_{anim.file_unique_id}.gif"
        return anim, filename

    # Video Note (round video) ────────────────────────────────────────────
    if message.video_note:
        vn: VideoNote = message.video_note
        filename = f"video_note_{vn.file_unique_id}.mp4"
        return vn, filename

    # Sticker ─────────────────────────────────────────────────────────────
    if message.sticker:
        sticker: Sticker = message.sticker
        ext = ".webp"
        if sticker.is_animated:
            ext = ".tgs"
        elif sticker.is_video:
            ext = ".webm"
        filename = f"sticker_{sticker.file_unique_id}{ext}"
        return sticker, filename

    raise ValueError(
        "هیچ فایل پشتیبانی‌شده‌ای در این پیام یافت نشد."
    )


async def download_file_bytes(file_obj: Any) -> bytes:
    """
    Download *file_obj* (any Telegram file type) and return raw bytes.
    Logs progress for large files.
    """
    tg_file = await file_obj.get_file()

    file_size = getattr(file_obj, "file_size", None)
    if file_size:
        mb = file_size / 1_048_576
        logger.info("Downloading %.1f MB from Telegram …", mb)
        if mb > WARN_MB:
            logger.warning(
                "Large file (%.1f MB). Make sure you are running a local "
                "Bot API server for files > 50 MB.",
                mb,
            )

    data = await tg_file.download_as_bytearray()
    logger.debug("Downloaded %d bytes.", len(data))
    return bytes(data)


# ── Internal ───────────────────────────────────────────────────────────────────


def _ext(mime_type: str | None, fallback: str) -> str:
    """Guess file extension from MIME type, or use *fallback*."""
    if mime_type:
        guessed = mimetypes.guess_extension(mime_type)
        if guessed:
            # mimetypes sometimes returns ".jpe" instead of ".jpg" etc.
            _fixes = {".jpe": ".jpg", ".jfif": ".jpg"}
            return _fixes.get(guessed, guessed)
    return fallback
