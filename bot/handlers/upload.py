"""
bot/handlers/upload.py
───────────────────────
Main message handler that processes any incoming file, downloads it,
uploads to GitHub, and replies with the result.

Flow
────
1. Authorisation check
2. Extract file object + original filename
3. Send "در حال پردازش…" feedback
4. Download bytes from Telegram
5. Upload to GitHub via GitHubService
6. Edit feedback message with rich success reply
7. Forward errors to admin (if configured)
"""

from __future__ import annotations

import logging

from telegram import Message, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.config.settings import get_settings
from bot.handlers.commands import get_user_path
from bot.services.file_service import download_file_bytes, extract_file_info
from bot.services.github_service import (
    AuthError,
    FileTooLargeError,
    GitHubError,
    GitHubService,
    PermissionError,
    RateLimitError,
)

logger = logging.getLogger(__name__)

# Singleton service – reuses the same httpx connection pool across calls
_github_service = GitHubService()


async def handle_file(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Entry point for all messages that contain a supported file."""
    cfg = get_settings()
    message: Message = update.effective_message  # type: ignore[assignment]
    user = update.effective_user

    if not user:
        return

    # ── 1. Authorisation ────────────────────────────────────────────────
    if not cfg.is_user_allowed(user.id):
        await message.reply_text(
            "⛔ *دسترسی رد شد.*\n"
            "شما در لیست کاربران مجاز نیستید.\n"
            "لطفاً با مدیر ربات تماس بگیرید.",
            parse_mode=ParseMode.MARKDOWN,
        )
        logger.warning("Unauthorized upload attempt by user %d (@%s).", user.id, user.username)
        return

    # ── 2. Extract file info ─────────────────────────────────────────────
    try:
        file_obj, filename = await extract_file_info(message)
    except ValueError as exc:
        await message.reply_text(f"⚠️ {exc}")
        return

    logger.info(
        "User %d (@%s) sent file: %s",
        user.id,
        user.username or "N/A",
        filename,
    )

    # ── 3. Send progress feedback ────────────────────────────────────────
    progress_msg = await message.reply_text(
        f"⏳ *در حال پردازش فایل…*\n📄 `{filename}`",
        parse_mode=ParseMode.MARKDOWN,
    )

    # ── 4. Download from Telegram ────────────────────────────────────────
    try:
        await progress_msg.edit_text(
            f"⬇️ *در حال دانلود از Telegram…*\n📄 `{filename}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        file_bytes = await download_file_bytes(file_obj)
    except Exception as exc:
        logger.error("Failed to download file '%s': %s", filename, exc)
        await progress_msg.edit_text(
            f"❌ *خطا در دانلود فایل*\n\n`{exc}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _notify_admin(context, user.id, filename, exc)
        return

    size_mb = len(file_bytes) / 1_048_576

    # ── 5. Upload to GitHub ──────────────────────────────────────────────
    try:
        await progress_msg.edit_text(
            f"⬆️ *در حال آپلود به GitHub…*\n"
            f"📄 `{filename}` ({size_mb:.2f} MB)",
            parse_mode=ParseMode.MARKDOWN,
        )

        custom_folder = get_user_path(user.id)
        result = await _github_service.upload_file(
            file_bytes=file_bytes,
            original_filename=filename,
            custom_folder=custom_folder,
        )
    except FileTooLargeError as exc:
        logger.warning("File too large for GitHub: %s", filename)
        await progress_msg.edit_text(
            f"📦 *فایل بسیار بزرگ است!*\n\n"
            f"{exc}\n\n"
            "💡 *پیشنهاد:* از [Git LFS](https://git-lfs.com) یا یک سرویس "
            "ابری مانند S3 / Cloudflare R2 استفاده کنید.",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )
        return
    except RateLimitError as exc:
        await progress_msg.edit_text(
            f"🚦 *محدودیت نرخ GitHub!*\n\n{exc}",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    except AuthError as exc:
        await progress_msg.edit_text(
            f"🔑 *خطای احراز هویت GitHub*\n\n{exc}",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _notify_admin(context, user.id, filename, exc)
        return
    except PermissionError as exc:
        await progress_msg.edit_text(
            f"🔒 *خطای دسترسی GitHub*\n\n{exc}",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _notify_admin(context, user.id, filename, exc)
        return
    except GitHubError as exc:
        logger.error("GitHub upload failed for '%s': %s", filename, exc)
        await progress_msg.edit_text(
            f"❌ *آپلود ناموفق بود!*\n\n{exc}",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _notify_admin(context, user.id, filename, exc)
        return
    except Exception as exc:
        logger.exception("Unexpected error during upload of '%s'", filename)
        await progress_msg.edit_text(
            "❌ *یک خطای غیرمنتظره رخ داد.*\n"
            "لطفاً دوباره امتحان کنید یا با مدیر تماس بگیرید.",
            parse_mode=ParseMode.MARKDOWN,
        )
        await _notify_admin(context, user.id, filename, exc)
        return

    # ── 6. Success reply ─────────────────────────────────────────────────
    action_label = "🔄 بازنویسی شد" if result.was_overwrite else "✅ آپلود شد"
    cfg = get_settings()

    success_text = (
        f"{action_label} *فایل با موفقیت ذخیره شد!*\n\n"
        f"📄 *نام فایل:* `{filename}`\n"
        f"📦 *حجم:* `{size_mb:.2f} MB`\n"
        f"📁 *مسیر در مخزن:* `{result.path}`\n"
        f"🌿 *شاخه:* `{cfg.github_branch}`\n"
        f"🔑 *کامیت:* `{result.sha[:10]}…`\n\n"
        f"🔗 [مشاهده در GitHub]({result.html_url})\n"
        f"📥 [دانلود مستقیم]({result.raw_url})"
    )

    await progress_msg.edit_text(
        success_text,
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )

    logger.info(
        "Upload complete: user=%d file='%s' path='%s' commit=%s",
        user.id,
        filename,
        result.path,
        result.sha[:10],
    )


# ── Admin notification ──────────────────────────────────────────────────────────

async def _notify_admin(
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    filename: str,
    error: Exception,
) -> None:
    cfg = get_settings()
    if not cfg.admin_user_id:
        return
    try:
        await context.bot.send_message(
            chat_id=cfg.admin_user_id,
            text=(
                f"⚠️ *گزارش خطا*\n\n"
                f"👤 کاربر: `{user_id}`\n"
                f"📄 فایل: `{filename}`\n"
                f"❌ خطا: `{type(error).__name__}: {error}`"
            ),
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as notify_exc:
        logger.warning("Could not notify admin: %s", notify_exc)
