"""
bot/services/file_service.py
─────────────────────────────
Helpers for resolving the Telegram file object from a Pyrogram Message,
extracting a meaningful filename, and downloading the raw bytes.

Pyrogram downloads files via client.download_media() which streams
internally and supports files up to 2 GB natively over MTProto —
no local Bot API server required.
"""

from __future__ import annotations

import io
import logging
import mimetypes
from typing import Any

from pyrogram import Client
from pyrogram.types import (
    Animation,
    Audio,
    Document,
    Message,
    Photo,
    Sticker,
    Video,
    VideoNote,
    Voice,
)

logger = logging.getLogger(__name__)

WARN_MB = 50  # Log a notice for files larger than this


# ── Public helpers ─────────────────────────────────────────────────────────────


def extract_file_info(message: Message) -> tuple[Any, str]:
    """
    Return *(file_object, filename)* for the first recognised attachment
    in *message*.  Raises ValueError if no supported attachment is found.

    This is a synchronous function — Pyrogram file objects carry all
    metadata eagerly; no network call is needed just to read the filename.

    Priority: Document first (preserves original filename), then the rest.
    """
    # Document  ──────────────────────────────────────────────────────────
    if message.document:
        doc: Document = message.document
        filename = doc.file_name or f"document_{doc.file_unique_id}"
        return doc, filename

    # Photo ──────────────────────────────────────────────────────────────
    # Pyrogram exposes the highest-resolution photo directly as message.photo
    if message.photo:
        photo: Photo = message.photo
        filename = f"photo_{photo.file_unique_id}.jpg"
        return photo, filename

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


async def download_file_bytes(client: Client, file_obj: Any) -> bytes:
    """
    Download *file_obj* (any Pyrogram file type) and return raw bytes.

    Uses client.download_media(in_memory=True) so nothing is written to
    disk.  Pyrogram returns a BytesIO when in_memory=True.
    Supports files up to 2 GB natively over MTProto.
    """
    file_size = getattr(file_obj, "file_size", None)
    if file_size:
        mb = file_size / 1_048_576
        logger.info("Downloading %.1f MB from Telegram ...", mb)
        if mb > WARN_MB:
            logger.warning(
                "Large file (%.1f MB). Download may take a while.",
                mb,
            )

    result = await client.download_media(file_obj, in_memory=True)

    if isinstance(result, io.BytesIO):
        data = result.getvalue()
    elif isinstance(result, (bytes, bytearray)):
        data = bytes(result)
    else:
        raise RuntimeError(
            f"download_media returned unexpected type: {type(result)}"
        )

    logger.debug("Downloaded %d bytes.", len(data))
    return data


# ── Internal ───────────────────────────────────────────────────────────────────


def _ext(mime_type: str | None, fallback: str) -> str:
    """Guess file extension from MIME type, or use *fallback*."""
    if mime_type:
        guessed = mimetypes.guess_extension(mime_type)
        if guessed:
            _fixes = {".jpe": ".jpg", ".jfif": ".jpg"}
            return _fixes.get(guessed, guessed)
    return fallback
