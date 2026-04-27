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
    telegram_api_id: int                  # From https://my.telegram.org
    telegram_api_hash: str                # From https://my.telegram.org
    telegram_local_server_url: str        # e.g. "http://localhost:8081"

    # ── GitHub ────────────────────────────────────────────────────────────
    github_token: str
    github_owner: str
    github_repo: str
    github_branch: str

    # ── Upload behaviour ─────────────────────────────────────────────────
    upload_base_path: str
    file_conflict_strategy: Literal["overwrite", "version"]

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

        # TELEGRAM_API_ID must be a valid integer
        api_id_raw = self._require("TELEGRAM_API_ID")
        try:
            self.telegram_api_id = int(api_id_raw)
        except ValueError:
            raise ValueError(
                "TELEGRAM_API_ID must be a number. "
                "Get it from https://my.telegram.org."
            )

        # TELEGRAM_LOCAL_SERVER_URL is required — this bot runs on its own server
        self.telegram_local_server_url = self._require("TELEGRAM_LOCAL_SERVER_URL").rstrip("/")

        # ── Optional with defaults ─────────────────────────────────────────
        self.github_branch = os.getenv("GITHUB_BRANCH", "main")
        self.upload_base_path = os.getenv("UPLOAD_BASE_PATH", "uploads").strip("/")

        conflict_raw = os.getenv("FILE_CONFLICT_STRATEGY", "version").lower()
        if conflict_raw not in ("overwrite", "version"):
            raise ValueError(
                f"FILE_CONFLICT_STRATEGY must be 'overwrite' or 'version', got '{conflict_raw}'"
            )
        self.file_conflict_strategy = conflict_raw  # type: ignore[assignment]

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

    def is_user_allowed(self, user_id: int) -> bool:
        """Return True if the user_id is in the whitelist (or whitelist is empty = open)."""
        if not self.allowed_user_ids:
            return True
        return user_id in self.allowed_user_ids

    def __repr__(self) -> str:
        return (
            f"<Settings owner={self.github_owner} repo={self.github_repo} "
            f"branch={self.github_branch} conflict={self.file_conflict_strategy} "
            f"local_server={self.telegram_local_server_url}>"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the singleton Settings instance.
    Cached so the .env file is only parsed once per process lifetime.
    """
    return Settings()
