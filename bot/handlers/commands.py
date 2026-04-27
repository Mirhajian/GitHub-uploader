"""
bot/handlers/commands.py
─────────────────────────
Handles /start, /help, /setpath, /clearpath, and /status commands.
Uses Pyrogram (MTProto).  All text strings are in Persian.
"""

from __future__ import annotations

import logging

from pyrogram import Client
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

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

async def cmd_start(client: Client, message: Message) -> None:
    cfg = get_settings()
    user = message.from_user
    if not user:
        return

    if not cfg.is_user_allowed(user.id):
        await message.reply("⛔ شما مجاز به استفاده از این ربات نیستید.")
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📂 راهنما", callback_data="show_help"),
            InlineKeyboardButton("⚙️ وضعیت", callback_data="show_status"),
        ],
        [
            InlineKeyboardButton("📁 تنظیم مسیر", callback_data="show_setpath_help"),
        ],
    ])

    welcome_text = (
        f"👋 سلام، **{user.first_name}**!\n\n"
        "🤖 به ربات آپلود فایل به GitHub خوش آمدید.\n\n"
        "📤 **نحوه استفاده:**\n"
        "کافی است هر فایلی (سند، عکس، ویدیو، صدا، و ...) را مستقیماً "
        "برای این ربات ارسال کنید.\n"
        "ربات آن را به صورت خودکار در مخزن GitHub آپلود می‌کند.\n\n"
        f"🗂 **مخزن:** `{cfg.github_owner}/{cfg.github_repo}`\n"
        f"🌿 **شاخه:** `{cfg.github_branch}`\n\n"
        "برای مشاهده دستورات کامل روی **راهنما** کلیک کنید."
    )

    await message.reply(welcome_text, reply_markup=keyboard)


# ── /help ──────────────────────────────────────────────────────────────────────

HELP_TEXT = """
📖 **راهنمای ربات**

━━━━━━━━━━━━━━━━━━━━
📤 **آپلود فایل**
فقط فایل موردنظر را ارسال کنید. ربات آن را دریافت و در GitHub ذخیره می‌کند.

━━━━━━━━━━━━━━━━━━━━
🗂 **دستورات**

`/start` — شروع و نمایش خوش‌آمدگویی
`/help` — نمایش این راهنما
`/setpath <مسیر>` — تنظیم پوشه سفارشی برای آپلود
`/clearpath` — پاکسازی مسیر سفارشی (بازگشت به پیش‌فرض)
`/status` — نمایش اطلاعات مخزن و تنظیمات فعلی

━━━━━━━━━━━━━━━━━━━━
📝 **نمونه مسیرسازی**

• پیش‌فرض: `uploads/YYYY-MM-DD/نام_فایل`
• با `/setpath پروژه/من`: `uploads/پروژه/من/نام_فایل`

━━━━━━━━━━━━━━━━━━━━
⚠️ **محدودیت‌ها**

• حداکثر حجم فایل GitHub: ۱۰۰ مگابایت
• حداکثر حجم فایل Telegram (MTProto): ۲۰۰۰ مگابایت
• برای فایل‌های بزرگ‌تر از ۱۰۰ مگابایت از Git LFS استفاده کنید

━━━━━━━━━━━━━━━━━━━━
✅ **فرمت‌های پشتیبانی‌شده**
سند، عکس، ویدیو، صدا، ویس، انیمیشن، ویدیو گرد، استیکر و تمام فایل‌های دیگر
"""


async def cmd_help(client: Client, message: Message) -> None:
    cfg = get_settings()
    user = message.from_user
    if not user:
        return
    if not cfg.is_user_allowed(user.id):
        await message.reply("⛔ شما مجاز به استفاده از این ربات نیستید.")
        return
    await message.reply(HELP_TEXT)


# ── /setpath ───────────────────────────────────────────────────────────────────

async def cmd_setpath(client: Client, message: Message) -> None:
    cfg = get_settings()
    user = message.from_user
    if not user:
        return
    if not cfg.is_user_allowed(user.id):
        await message.reply("⛔ شما مجاز به استفاده از این ربات نیستید.")
        return

    # message.command is ["setpath", "arg1", "arg2", ...]
    args = message.command[1:]
    if not args:
        await message.reply(
            "⚠️ لطفاً یک مسیر مشخص کنید.\n\n"
            "مثال: `/setpath پروژه/تصاویر`"
        )
        return

    path = "/".join(args).strip("/")
    set_user_path(user.id, path)
    logger.info("User %d set custom path: %s", user.id, path)

    await message.reply(
        f"✅ **مسیر آپلود تنظیم شد:**\n"
        f"`{cfg.upload_base_path}/{path}/`\n\n"
        "فایل‌های بعدی شما در این مسیر ذخیره می‌شوند."
    )


# ── /clearpath ─────────────────────────────────────────────────────────────────

async def cmd_clearpath(client: Client, message: Message) -> None:
    cfg = get_settings()
    user = message.from_user
    if not user:
        return
    if not cfg.is_user_allowed(user.id):
        await message.reply("⛔ شما مجاز به استفاده از این ربات نیستید.")
        return

    clear_user_path(user.id)
    await message.reply(
        "🗑 **مسیر سفارشی پاک شد.**\n"
        "فایل‌های بعدی در مسیر پیش‌فرض (`uploads/تاریخ_امروز/`) ذخیره می‌شوند."
    )


# ── /status ────────────────────────────────────────────────────────────────────

async def cmd_status(client: Client, message: Message) -> None:
    cfg = get_settings()
    user = message.from_user
    if not user:
        return
    if not cfg.is_user_allowed(user.id):
        await message.reply("⛔ شما مجاز به استفاده از این ربات نیستید.")
        return

    custom_path = get_user_path(user.id)
    path_display = (
        f"`{cfg.upload_base_path}/{custom_path}/`"
        if custom_path
        else f"`{cfg.upload_base_path}/YYYY-MM-DD/` *(پیش‌فرض)*"
    )
    conflict_fa = "بازنویسی" if cfg.file_conflict_strategy == "overwrite" else "ایجاد نسخه جدید"

    status_text = (
        "⚙️ **وضعیت فعلی ربات**\n\n"
        f"🗂 **مخزن:** `{cfg.github_owner}/{cfg.github_repo}`\n"
        f"🌿 **شاخه:** `{cfg.github_branch}`\n"
        f"📁 **مسیر آپلود:** {path_display}\n"
        f"⚠️ **تداخل فایل:** {conflict_fa}\n"
        f"🌐 **حالت اتصال:** MTProto (Pyrogram)\n"
    )

    await message.reply(status_text)


# ── Callback query handler for inline buttons ──────────────────────────────────

async def callback_handler(client: Client, query: CallbackQuery) -> None:
    """
    Handle inline keyboard button presses.

    IMPORTANT: query.from_user is the human who pressed the button.
    query.message.from_user is the *bot* that sent the message — never
    use query.message for user identity checks.
    """
    await query.answer()

    if query.data == "show_help":
        await query.message.reply(HELP_TEXT)

    elif query.data == "show_status":
        # Build a status reply using the identity of the button-presser,
        # not the bot that owns query.message.
        cfg = get_settings()
        user = query.from_user
        if not user or not cfg.is_user_allowed(user.id):
            await query.message.reply("⛔ شما مجاز به استفاده از این ربات نیستید.")
            return

        custom_path = get_user_path(user.id)
        path_display = (
            f"`{cfg.upload_base_path}/{custom_path}/`"
            if custom_path
            else f"`{cfg.upload_base_path}/YYYY-MM-DD/` *(پیش‌فرض)*"
        )
        conflict_fa = (
            "بازنویسی" if cfg.file_conflict_strategy == "overwrite" else "ایجاد نسخه جدید"
        )
        await query.message.reply(
            "⚙️ **وضعیت فعلی ربات**\n\n"
            f"🗂 **مخزن:** `{cfg.github_owner}/{cfg.github_repo}`\n"
            f"🌿 **شاخه:** `{cfg.github_branch}`\n"
            f"📁 **مسیر آپلود:** {path_display}\n"
            f"⚠️ **تداخل فایل:** {conflict_fa}\n"
            f"🌐 **حالت اتصال:** MTProto (Pyrogram)\n"
        )

    elif query.data == "show_setpath_help":
        await query.message.reply(
            "📁 **تنظیم مسیر آپلود**\n\n"
            "برای تنظیم پوشه سفارشی دستور زیر را ارسال کنید:\n\n"
            "`/setpath نام_پوشه`\n\n"
            "مثال:\n"
            "`/setpath پروژه/تصاویر`"
        )
