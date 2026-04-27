# 📤 Telegram → GitHub File Upload Bot

> نسخه فارسی این راهنما موجود است: [README.fa.md](README.fa.md)

A Telegram bot that receives any file type and uploads it directly to a GitHub repository via the Contents API.

> **No local Bot API server required** — the bot uses **Pyrogram** which connects directly to Telegram's servers over the MTProto protocol, supporting files up to **2 GB** natively.

---

## Features

- **All file types** — documents, photos, videos, audio, voice, stickers, animations, video notes
- **Direct MTProto connection** — no middleware server, up to 2 GB uploads/downloads out of the box
- **Access control** — whitelist of allowed Telegram user IDs
- **Conflict resolution** — overwrite existing files or auto-version them (`file_1.ext`, `file_2.ext`, …)
- **Custom upload paths** — per-user `/setpath` command
- **Retry logic** — exponential back-off on GitHub secondary rate limits
- **Admin notifications** — errors forwarded to a configured admin user
- **Rotating log file** — 10 MB × 5 backups

---

## Project Structure

```
telegram-github-uploader/
├── bot/
│   ├── __init__.py
│   ├── __main__.py            # Entry point – run with `python -m bot`
│   ├── config/
│   │   ├── __init__.py
│   │   ├── settings.py        # All env-var configuration
│   │   └── logging_config.py  # Root logger setup
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── commands.py        # /start /help /setpath /clearpath /status
│   │   └── upload.py          # Main file-upload message handler
│   └── services/
│       ├── __init__.py
│       ├── file_service.py    # Telegram file extraction & download
│       └── github_service.py  # GitHub Contents API wrapper
├── logs/                      # Auto-created at runtime
├── .env                       # Your secrets (never commit this)
├── .env.example               # Template – copy and fill in
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/mirhajian/GitHub-uploader
cd GitHub-uploader

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env and fill in the required values
```

#### Required variables

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_API_ID` | From [my.telegram.org](https://my.telegram.org) |
| `TELEGRAM_API_HASH` | From [my.telegram.org](https://my.telegram.org) |
| `GITHUB_TOKEN` | PAT with `repo` scope (read/write contents) |
| `GITHUB_OWNER` | Your GitHub username or org |
| `GITHUB_REPO` | Target repository name |

#### Optional variables

| Variable | Default | Description |
|---|---|---|
| `GITHUB_BRANCH` | `main` | Target branch |
| `UPLOAD_BASE_PATH` | `uploads` | Root folder inside the repo |
| `FILE_CONFLICT_STRATEGY` | `version` | `overwrite` or `version` |
| `ALLOWED_USER_IDS` | *(empty = open)* | Comma-separated Telegram user IDs |
| `ADMIN_USER_ID` | *(none)* | Receives error notifications |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `LOG_FILE` | `logs/bot.log` | Log file path |

### 3. Run the bot

```bash
python -m bot
```

That's it. No local Bot API server needed — Pyrogram handles everything over MTProto directly.

---

## Getting Your Credentials

### Telegram API ID & Hash (`TELEGRAM_API_ID`, `TELEGRAM_API_HASH`)

Required by Pyrogram for the direct MTProto connection.

1. Go to [my.telegram.org](https://my.telegram.org) and sign in with your phone number.
2. Click **"API development tools"**.
3. Fill in a short app name (anything, e.g. `my-bot`) and click **"Create application"**.
4. Copy the `App api_id` (number) and `App api_hash` (string).

> ⚠️ Never share these or commit them to a public repository.

### Bot Token (`TELEGRAM_BOT_TOKEN`)

1. Open [@BotFather](https://t.me/BotFather) in Telegram and send `/newbot`.
2. Follow the prompts to pick a name and username.
3. Copy the token BotFather gives you.

### GitHub Token (`GITHUB_TOKEN`)

1. On GitHub go to **Settings → Developer settings → Personal access tokens → Tokens (classic)**.
2. Click **Generate new token (classic)**.
3. Give it a descriptive name, set an expiry, and tick the **`repo`** scope.
4. Click **Generate token** and copy it immediately — it won't be shown again.

> ⚠️ Never commit this token or share it.

### Your Telegram User ID (`ALLOWED_USER_IDS`, `ADMIN_USER_ID`)

Send `/start` to [@userinfobot](https://t.me/userinfobot) — it will reply with your numeric user ID.

---

## Bot Commands

| Command | Description |
|---|---|
| `/start` | Welcome message with inline buttons |
| `/help` | Full help text |
| `/setpath <folder>` | Set a custom upload sub-folder |
| `/clearpath` | Reset to the default date-based path |
| `/status` | Show current configuration |

---

## File Size Limits

| Layer | Maximum |
|---|---|
| Pyrogram / MTProto (download from Telegram) | **2 000 MB** |
| GitHub Contents API (upload to repo) | **100 MB** |

For files larger than 100 MB, use [Git LFS](https://git-lfs.com) or an object storage service (S3, Cloudflare R2, etc.).

---

## Upload Path Format

```
{UPLOAD_BASE_PATH}/{folder}/{filename}

# Default (no /setpath):
uploads/2024-01-15/photo.jpg

# With /setpath project/images:
uploads/project/images/photo.jpg
```

