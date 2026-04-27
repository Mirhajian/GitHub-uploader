"""
bot/handlers/commands.py
─────────────────────────
Handles /start, /help, /setpath, and /status commands.
All text strings are in Persian.
"""

from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.config.settings import get_settings

logger = logging.getLogger(__name__)

# In-memory per-user custom upload paths  { user_id: "my/folder" }
_user_paths: dict[int, str] = {}


def get_user_path(user_id: int) -> str | None:
    return _user_paths.get(user_id)


def set_user_path(user_id: int, path: str) -> None:
    _user_paths[user_id] = path


def clear_user_path(user_id: int) -> None:
    _user_paths.pop(user_id, None)


# ── /start ─────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = get_settings()
    user = update.effective_user
    if not user:
        return

    if not cfg.is_user_allowed(user.id):
        await update.message.reply_text(
            "⛔ شما مجاز به استفاده از این ربات نیستید."
        )
        return

    keyboard = [
        [
            InlineKeyboardButton("📂 راهنما", callback_data="show_help"),
            InlineKeyboardButton("⚙️ وضعیت", callback_data="show_status"),
        ],
        [
            InlineKeyboardButton("📁 تنظیم مسیر", callback_data="show_setpath_help"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    welcome_text = (
        f"👋 سلام، *{user.first_name}*!\n\n"
        "🤖 به ربات آپلود فایل به GitHub خوش آمدید.\n\n"
        "📤 *نحوه استفاده:*\n"
        "کافی است هر فایلی (سند، عکس، ویدیو، صدا، و ...) را مستقیماً "
        "برای این ربات ارسال کنید.\n"
        "ربات آن را به صورت خودکار در مخزن GitHub آپلود می‌کند.\n\n"
        f"🗂 *مخزن:* `{cfg.github_owner}/{cfg.github_repo}`\n"
        f"🌿 *شاخه:* `{cfg.github_branch}`\n\n"
        "برای مشاهده دستورات کامل روی *راهنما* کلیک کنید."
    )

    await update.message.reply_text(
        welcome_text,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup,
    )


# ── /help ──────────────────────────────────────────────────────────────────────

HELP_TEXT = """
📖 *راهنمای ربات*

━━━━━━━━━━━━━━━━━━━━
📤 *آپلود فایل*
فقط فایل موردنظر را ارسال کنید. ربات آن را دریافت و در GitHub ذخیره می‌کند.

━━━━━━━━━━━━━━━━━━━━
🗂 *دستورات*

`/start` — شروع و نمایش خوش‌آمدگویی
`/help` — نمایش این راهنما
`/setpath <مسیر>` — تنظیم پوشه سفارشی برای آپلود
`/clearpath` — پاکسازی مسیر سفارشی (بازگشت به پیش‌فرض)
`/status` — نمایش اطلاعات مخزن و تنظیمات فعلی

━━━━━━━━━━━━━━━━━━━━
📝 *نمونه مسیرسازی*

• پیش‌فرض: `uploads/YYYY-MM-DD/نام_فایل`
• با `/setpath پروژه/من`: `uploads/پروژه/من/نام_فایل`

━━━━━━━━━━━━━━━━━━━━
⚠️ *محدودیت‌ها*

• حداکثر حجم فایل GitHub: ۱۰۰ مگابایت
• برای فایل‌های بزرگ‌تر از ۵۰ مگابایت نیاز به سرور Bot API محلی دارید
• برای فایل‌های بزرگ‌تر از ۱۰۰ مگابایت از Git LFS استفاده کنید

━━━━━━━━━━━━━━━━━━━━
✅ *فرمت‌های پشتیبانی‌شده*
سند، عکس، ویدیو، صدا، ویس، انیمیشن، ویدیو گرد، استیکر و تمام فایل‌های دیگر
"""


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = get_settings()
    user = update.effective_user
    if not user:
        return

    if not cfg.is_user_allowed(user.id):
        await update.message.reply_text("⛔ شما مجاز به استفاده از این ربات نیستید.")
        return

    await update.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)


# ── /setpath ───────────────────────────────────────────────────────────────────

async def cmd_setpath(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = get_settings()
    user = update.effective_user
    if not user:
        return

    if not cfg.is_user_allowed(user.id):
        await update.message.reply_text("⛔ شما مجاز به استفاده از این ربات نیستید.")
        return

    if not context.args:
        await update.message.reply_text(
            "⚠️ لطفاً یک مسیر مشخص کنید.\n\n"
            "مثال: `/setpath پروژه/تصاویر`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    path = "/".join(context.args).strip("/")
    set_user_path(user.id, path)
    logger.info("User %d set custom path: %s", user.id, path)

    await update.message.reply_text(
        f"✅ *مسیر آپلود تنظیم شد:*\n"
        f"`{cfg.upload_base_path}/{path}/`\n\n"
        "فایل‌های بعدی شما در این مسیر ذخیره می‌شوند.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /clearpath ─────────────────────────────────────────────────────────────────

async def cmd_clearpath(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = get_settings()
    user = update.effective_user
    if not user:
        return

    if not cfg.is_user_allowed(user.id):
        await update.message.reply_text("⛔ شما مجاز به استفاده از این ربات نیستید.")
        return

    clear_user_path(user.id)
    await update.message.reply_text(
        "🗑 *مسیر سفارشی پاک شد.*\n"
        "فایل‌های بعدی در مسیر پیش‌فرض (`uploads/تاریخ_امروز/`) ذخیره می‌شوند.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ── /status ────────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    cfg = get_settings()
    user = update.effective_user
    if not user:
        return

    if not cfg.is_user_allowed(user.id):
        await update.message.reply_text("⛔ شما مجاز به استفاده از این ربات نیستید.")
        return

    custom_path = get_user_path(user.id)
    path_display = f"`{cfg.upload_base_path}/{custom_path}/`" if custom_path else f"`{cfg.upload_base_path}/YYYY-MM-DD/` *(پیش‌فرض)*"

    conflict_fa = "بازنویسی" if cfg.file_conflict_strategy == "overwrite" else "ایجاد نسخه جدید"
    server_mode = "سرور محلی Bot API" if cfg.telegram_local_server_url else "سرورهای رسمی Telegram"

    status_text = (
        "⚙️ *وضعیت فعلی ربات*\n\n"
        f"🗂 *مخزن:* `{cfg.github_owner}/{cfg.github_repo}`\n"
        f"🌿 *شاخه:* `{cfg.github_branch}`\n"
        f"📁 *مسیر آپلود:* {path_display}\n"
        f"⚠️ *تداخل فایل:* {conflict_fa}\n"
        f"🌐 *حالت سرور:* {server_mode}\n"
    )

    await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN)


# ── Callback query handler for inline buttons ──────────────────────────────────

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    if query.data == "show_help":
        await query.message.reply_text(HELP_TEXT, parse_mode=ParseMode.MARKDOWN)
    elif query.data == "show_status":
        # Re-use status logic via a fake update
        await cmd_status(update, context)
    elif query.data == "show_setpath_help":
        await query.message.reply_text(
            "📁 *تنظیم مسیر آپلود*\n\n"
            "برای تنظیم پوشه سفارشی دستور زیر را ارسال کنید:\n\n"
            "`/setpath نام_پوشه`\n\n"
            "مثال:\n"
            "`/setpath پروژه/تصاویر`",
            parse_mode=ParseMode.MARKDOWN,
        )
