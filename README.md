# 📤 Telegram → GitHub File Upload Bot

> یک نسخه فارسی این راهنما موجود است: [README.fa.md](README.fa.md)

A Telegram bot that receives any file type and uploads it directly to a GitHub repository via the Contents API.

---

## Features

- **All file types** — documents, photos, videos, audio, voice, stickers, animations, video notes
- **Access control** — whitelist of allowed Telegram user IDs
- **Conflict resolution** — overwrite existing files or auto-version them (`file_1.ext`, `file_2.ext`, …)
- **Custom upload paths** — per-user `/setpath` command
- **Self-hosted** — runs entirely on your own VPS via a local Telegram Bot API server (up to 2 GB files)
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
│   │   ├── __init__.py        # re-exports Settings, get_settings
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
├── Dockerfile
└── requirements.txt
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
# Edit .env and fill in TELEGRAM_BOT_TOKEN, GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO
```

#### Required variables

| Variable | Description |
|---|---|
| `TELEGRAM_BOT_TOKEN` | From [@BotFather](https://t.me/BotFather) |
| `TELEGRAM_API_ID` | From [my.telegram.org](https://my.telegram.org) |
| `TELEGRAM_API_HASH` | From [my.telegram.org](https://my.telegram.org) |
| `TELEGRAM_LOCAL_SERVER_URL` | URL of your running local Bot API server, e.g. `http://localhost:8081` |
| `GITHUB_TOKEN` | PAT with `repo` → `contents` read/write scope |
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

### 3. Set up and start the local Bot API server

The bot requires a self-hosted [Telegram Bot API server](https://github.com/tdlib/telegram-bot-api). It must be running before you start the bot.

**Install on Ubuntu/Debian:**

```bash
apt install telegram-bot-api
```

**Or build from source** (if not in your package manager):

```bash
apt install make git zlib1g-dev libssl-dev gperf cmake clang libc++-dev libc++abi-dev
git clone --recursive https://github.com/tdlib/telegram-bot-api.git
cd telegram-bot-api && mkdir build && cd build
cmake -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX:PATH=/usr/local ..
cmake --build . --target install
```

**Run the server** (get `api-id` and `api-hash` from [my.telegram.org](https://my.telegram.org)):

```bash
telegram-bot-api \
  --api-id=YOUR_API_ID \
  --api-hash=YOUR_API_HASH \
  --local \
  --http-port=8081 \
  --dir=/var/lib/telegram-bot-api
```

> Keep this running in the background (e.g. via `systemd` or `screen`) before starting the bot.

### 4. Run the bot

```bash
python -m bot
```

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

| Mode | Max upload | Max download |
|---|---|---|
| Local Bot API server (your VPS) | 2 000 MB | 2 000 MB |
| GitHub Contents API hard limit | **100 MB** | — |

For files > 100 MB, use [Git LFS](https://git-lfs.com) or an object storage service (S3, Cloudflare R2, etc.).

---

## Upload Path Format

```
{UPLOAD_BASE_PATH}/{folder}/{filename}

# Default (no /setpath):
uploads/2024-01-15/photo.jpg

# With /setpath project/images:
uploads/project/images/photo.jpg
```

