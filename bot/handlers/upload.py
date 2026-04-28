"""
bot/handlers/upload.py
───────────────────────
Main message handler: downloads the file from Telegram, uploads to GitHub
(via Contents API or Git LFS depending on size), and replies with result.

Flow
────
1. Authorisation check
2. Extract file object + original filename
3. Send "در حال پردازش…" feedback
4. Download bytes from Telegram via Pyrogram
5. Upload to GitHub via GitHubService (auto-routes to LFS if needed)
6. Edit feedback message with rich success reply
7. Forward errors to admin (if configured)
"""

from __future__ import annotations

import logging

from pyrogram import Client
from pyrogram.types import Message

from bot.config.settings import get_settings
from bot.handlers.commands import get_user_path
from bot.services.file_service import download_file_bytes, extract_file_info
from bot.services.github_service import (
    AuthError,
    FileTooLargeError,
    GitHubError,
    GitHubService,
    LFSNotEnabledError,
    PermissionError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

_github_service = GitHubService()


async def handle_file(client: Client, message: Message) -> None:
    """Entry point for all messages that contain a supported file."""
    cfg = get_settings()
    user = message.from_user

    if not user:
        return

    # ── 1. Authorisation ────────────────────────────────────────────────
    if not cfg.is_user_allowed(user.id):
        await message.reply(
            "⛔ *دسترسی رد شد.*\n"
            "شما در لیست کاربران مجاز نیستید.\n"
            "لطفاً با مدیر ربات تماس بگیرید.",
        )
        logger.warning("Unauthorized upload attempt by user %d (@%s).", user.id, user.username)
        return

    # ── 2. Extract file info ─────────────────────────────────────────────
    try:
        file_obj, filename = extract_file_info(message)
    except ValueError as exc:
        await message.reply(f"⚠️ {exc}")
        return

    logger.info("User %d (@%s) sent file: %s", user.id, user.username or "N/A", filename)

    # ── 3. Send progress feedback ────────────────────────────────────────
    progress_msg = await message.reply(f"⏳ *در حال پردازش فایل…*\n📄 `{filename}`")

    # ── 4. Download from Telegram ────────────────────────────────────────
    try:
        await progress_msg.edit_text(
            f"⬇️ *در حال دانلود از Telegram…*\n📄 `{filename}`",
        )
        file_bytes = await download_file_bytes(client, file_obj)
    except Exception as exc:
        logger.error("Failed to download file '%s': %s", filename, exc)
        await progress_msg.edit_text(f"❌ *خطا در دانلود فایل*\n\n`{exc}`")
        await _notify_admin(client, user.id, filename, exc)
        return

    size_mb = len(file_bytes) / 1_048_576
    lfs_label = " (Git LFS)" if len(file_bytes) >= cfg.lfs_threshold_bytes else ""

    # ── 5. Upload to GitHub ──────────────────────────────────────────────
    try:
        await progress_msg.edit_text(
            f"⬆️ *در حال آپلود به GitHub{lfs_label}…*\n"
            f"📄 `{filename}` ({size_mb:.2f} MB)",
        )
        custom_folder = get_user_path(user.id)
        result = await _github_service.upload_file(
            file_bytes=file_bytes,
            original_filename=filename,
            custom_folder=custom_folder,
        )
    except LFSNotEnabledError as exc:
        await progress_msg.edit_text(
            f"⚠️ *Git LFS فعال نیست!*\n\n{exc}",
        )
        return
    except FileTooLargeError as exc:
        await progress_msg.edit_text(
            f"📦 *فایل بسیار بزرگ است!*\n\n{exc}",
        )
        return
    except RateLimitError as exc:
        await progress_msg.edit_text(f"🚦 *محدودیت نرخ GitHub!*\n\n{exc}")
        return
    except AuthError as exc:
        await progress_msg.edit_text(f"🔑 *خطای احراز هویت GitHub*\n\n{exc}")
        await _notify_admin(client, user.id, filename, exc)
        return
    except PermissionError as exc:
        await progress_msg.edit_text(f"🔒 *خطای دسترسی GitHub*\n\n{exc}")
        await _notify_admin(client, user.id, filename, exc)
        return
    except GitHubError as exc:
        logger.error("GitHub upload failed for '%s': %s", filename, exc)
        await progress_msg.edit_text(f"❌ *آپلود ناموفق بود!*\n\n{exc}")
        await _notify_admin(client, user.id, filename, exc)
        return
    except Exception as exc:
        logger.exception("Unexpected error during upload of '%s'", filename)
        await progress_msg.edit_text(
            "❌ *یک خطای غیرمنتظره رخ داد.*\n"
            "لطفاً دوباره امتحان کنید یا با مدیر تماس بگیرید.",
        )
        await _notify_admin(client, user.id, filename, exc)
        return

    # ── 6. Success reply ─────────────────────────────────────────────────
    action_label = "🔄 بازنویسی شد" if result.was_overwrite else "✅ آپلود شد"
    storage_label = "☁️ Git LFS" if result.used_lfs else "📁 GitHub"

    success_text = (
        f"{action_label} *فایل با موفقیت ذخیره شد!*\n\n"
        f"📄 *نام فایل:* `{filename}`\n"
        f"📦 *حجم:* `{size_mb:.2f} MB`\n"
        f"🗄 *روش ذخیره:* {storage_label}\n"
        f"📁 *مسیر در مخزن:* `{result.path}`\n"
        f"🌿 *شاخه:* `{cfg.github_branch}`\n"
        f"🔑 *کامیت:* `{result.sha[:10]}…`\n\n"
        f"🔗 [مشاهده در GitHub]({result.html_url})\n"
        f"📥 [دانلود مستقیم]({result.raw_url})"
    )

    await progress_msg.edit_text(success_text, disable_web_page_preview=True)

    logger.info(
        "Upload complete: user=%d file='%s' path='%s' commit=%s lfs=%s",
        user.id, filename, result.path, result.sha[:10], result.used_lfs,
    )


# ── Admin notification ──────────────────────────────────────────────────────────

async def _notify_admin(
    client: Client,
    user_id: int,
    filename: str,
    error: Exception,
) -> None:
    cfg = get_settings()
    if not cfg.admin_user_id:
        return
    try:
        await client.send_message(
            chat_id=cfg.admin_user_id,
            text=(
                f"⚠️ *گزارش خطا*\n\n"
                f"👤 کاربر: `{user_id}`\n"
                f"📄 فایل: `{filename}`\n"
                f"❌ خطا: `{type(error).__name__}: {error}`"
            ),
        )
    except Exception as notify_exc:
        logger.warning("Could not notify admin: %s", notify_exc)
