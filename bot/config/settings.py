"""
bot/config/settings.py
─────────────────────
Central configuration loaded once from the .env file via python-dotenv.
All other modules should import `get_settings()` instead of reading
environment variables directly.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from dotenv import load_dotenv

load_dotenv()


class Settings:
    """
    Immutable settings object built from environment variables.
    Raises ValueError on startup if a required variable is missing.
    """

    # ── Telegram ──────────────────────────────────────────────────────────
    telegram_bot_token: str
    telegram_api_id: int    # From https://my.telegram.org
    telegram_api_hash: str  # From https://my.telegram.org

    # ── GitHub ────────────────────────────────────────────────────────────
    github_token: str
    github_owner: str
    github_repo: str
    github_branch: str
    lfs_threshold_mb: float   # Files >= this size go through Git LFS

    # ── Upload behaviour ──────────────────────────────────────────────────
    upload_base_path: str
    file_conflict_strategy: Literal["overwrite", "version"]

    # ── VPS disk cleanup ──────────────────────────────────────────────────
    # When enabled the bot deletes the oldest uploaded files from the repo
    # once total size exceeds the configured cap, keeping disk usage low
    # for minimal (10 GB SSD) VPS deployments.
    cleanup_enabled: bool
    cleanup_max_repo_mb: float   # Trigger cleanup above this repo size (MB)
    cleanup_keep_latest: int     # Number of most-recent files to always keep

    # ── Access control ────────────────────────────────────────────────────
    allowed_user_ids: set[int]
    admin_user_id: int | None

    # ── Logging ───────────────────────────────────────────────────────────
    log_level: str
    log_file: str

    def __init__(self) -> None:
        # ── Required ──────────────────────────────────────────────────────
        self.telegram_bot_token = self._require("TELEGRAM_BOT_TOKEN")
        self.telegram_api_hash = self._require("TELEGRAM_API_HASH")
        self.github_token = self._require("GITHUB_TOKEN")
        self.github_owner = self._require("GITHUB_OWNER")
        self.github_repo = self._require("GITHUB_REPO")

        api_id_raw = self._require("TELEGRAM_API_ID")
        try:
            self.telegram_api_id = int(api_id_raw)
        except ValueError:
            raise ValueError(
                "TELEGRAM_API_ID must be a number. "
                "Get it from https://my.telegram.org."
            )

        # ── Optional with defaults ─────────────────────────────────────────
        self.github_branch = os.getenv("GITHUB_BRANCH", "main")
        self.upload_base_path = os.getenv("UPLOAD_BASE_PATH", "uploads").strip("/")

        conflict_raw = os.getenv("FILE_CONFLICT_STRATEGY", "version").lower()
        if conflict_raw not in ("overwrite", "version"):
            raise ValueError(
                f"FILE_CONFLICT_STRATEGY must be 'overwrite' or 'version', got '{conflict_raw}'"
            )
        self.file_conflict_strategy = conflict_raw  # type: ignore[assignment]

        # LFS: files >= this many MB are uploaded via Git LFS instead of
        # the Contents API (which hard-limits at 100 MB).
        # Default 50 MB — well under GitHub's 100 MB Contents API limit,
        # leaving headroom and enabling LFS for large-media users.
        try:
            self.lfs_threshold_mb = float(os.getenv("LFS_THRESHOLD_MB", "50"))
        except ValueError:
            raise ValueError("LFS_THRESHOLD_MB must be a number (e.g. 50).")

        # Disk cleanup
        self.cleanup_enabled = os.getenv("CLEANUP_ENABLED", "false").lower() in (
            "1", "true", "yes"
        )
        try:
            self.cleanup_max_repo_mb = float(os.getenv("CLEANUP_MAX_REPO_MB", "800"))
        except ValueError:
            raise ValueError("CLEANUP_MAX_REPO_MB must be a number (e.g. 800).")
        try:
            self.cleanup_keep_latest = int(os.getenv("CLEANUP_KEEP_LATEST", "10"))
        except ValueError:
            raise ValueError("CLEANUP_KEEP_LATEST must be an integer (e.g. 10).")

        raw_ids = os.getenv("ALLOWED_USER_IDS", "")
        self.allowed_user_ids = {
            int(uid.strip())
            for uid in raw_ids.split(",")
            if uid.strip().lstrip("-").isdigit()
        }

        admin_raw = os.getenv("ADMIN_USER_ID", "")
        self.admin_user_id = int(admin_raw) if admin_raw.lstrip("-").isdigit() else None

        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        self.log_file = os.getenv("LOG_FILE", "logs/bot.log")

    # ── Helpers ───────────────────────────────────────────────────────────
    @staticmethod
    def _require(key: str) -> str:
        value = os.getenv(key, "").strip()
        if not value:
            raise ValueError(
                f"Required environment variable '{key}' is missing or empty. "
                "Please check your .env file."
            )
        return value

    @property
    def github_api_base(self) -> str:
        return "https://api.github.com"

    @property
    def repo_contents_url(self) -> str:
        return (
            f"{self.github_api_base}/repos/{self.github_owner}"
            f"/{self.github_repo}/contents"
        )

    @property
    def lfs_threshold_bytes(self) -> int:
        return int(self.lfs_threshold_mb * 1024 * 1024)

    def is_user_allowed(self, user_id: int) -> bool:
        if not self.allowed_user_ids:
            return True
        return user_id in self.allowed_user_ids

    def __repr__(self) -> str:
        return (
            f"<Settings owner={self.github_owner} repo={self.github_repo} "
            f"branch={self.github_branch} conflict={self.file_conflict_strategy} "
            f"lfs_threshold={self.lfs_threshold_mb}MB "
            f"cleanup={self.cleanup_enabled}>"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
