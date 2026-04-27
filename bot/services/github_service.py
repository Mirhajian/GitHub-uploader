"""
bot/services/github_service.py
──────────────────────────────
All interaction with the GitHub Contents API happens here.

Key behaviours
──────────────
• Async HTTP via `httpx.AsyncClient`.
• Exponential back-off with jitter when hitting secondary rate limits.
• Respects `x-ratelimit-remaining` header – logs a warning at < 100.
• Files ≥ 100 MB raise `FileTooLargeError` with an actionable message.
• Duplicate filenames are resolved via the strategy in Settings:
  - "overwrite"  → fetch existing SHA and PUT with it (GitHub requirement).
  - "version"    → append _1, _2, … until a free slot is found.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath

import httpx

from bot.config.settings import get_settings

logger = logging.getLogger(__name__)

# GitHub enforces a 100 MB hard limit for the Contents API.
GITHUB_MAX_BYTES = 100 * 1024 * 1024  # 100 MB
# We warn earlier so users aren't surprised.
GITHUB_WARN_BYTES = 50 * 1024 * 1024  # 50 MB

_MAX_RETRIES = 5
_BASE_BACKOFF = 1.0  # seconds


# ── Custom exceptions ──────────────────────────────────────────────────────────


class GitHubError(Exception):
    """Base class for GitHub service errors."""


class FileTooLargeError(GitHubError):
    """File exceeds GitHub Contents API size limit."""


class RateLimitError(GitHubError):
    """GitHub primary rate limit exceeded."""


class AuthError(GitHubError):
    """Invalid or expired GitHub token."""


class PermissionError(GitHubError):
    """Token lacks required permissions."""


# ── Result dataclass ───────────────────────────────────────────────────────────


@dataclass
class UploadResult:
    path: str           # path inside the repo, e.g. uploads/2024-01-15/photo.jpg
    sha: str            # commit SHA
    html_url: str       # GitHub blob URL
    raw_url: str        # raw.githubusercontent.com URL
    size_bytes: int
    was_overwrite: bool


# ── Service ────────────────────────────────────────────────────────────────────


class GitHubService:
    """Async wrapper around GitHub Contents API."""

    def __init__(self) -> None:
        self._cfg = get_settings()
        self._headers = {
            "Authorization": f"Bearer {self._cfg.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    # ── Public API ─────────────────────────────────────────────────────────

    async def upload_file(
        self,
        file_bytes: bytes,
        original_filename: str,
        custom_folder: str | None = None,
    ) -> UploadResult:
        """
        Upload *file_bytes* to GitHub and return an UploadResult.

        Args:
            file_bytes:        Raw content of the file.
            original_filename: Original filename (used for extension + naming).
            custom_folder:     Optional subfolder inside upload_base_path.
        """
        size = len(file_bytes)

        if size > GITHUB_MAX_BYTES:
            raise FileTooLargeError(
                f"فایل {size / 1_048_576:.1f} MB است. "
                "حداکثر حجم مجاز برای GitHub Contents API برابر ۱۰۰ مگابایت است.\n"
                "لطفاً از Git LFS یا یک سرویس ذخیره‌سازی دیگر استفاده کنید."
            )

        if size > GITHUB_WARN_BYTES:
            logger.warning(
                "File '%s' is %.1f MB – approaching GitHub 100 MB limit.",
                original_filename,
                size / 1_048_576,
            )

        repo_path = self._build_path(original_filename, custom_folder)

        async with httpx.AsyncClient(timeout=60.0) as client:
            existing_sha = await self._get_existing_sha(client, repo_path)

            if existing_sha and self._cfg.file_conflict_strategy == "version":
                repo_path = await self._next_free_path(client, repo_path)
                existing_sha = None  # definitely a new file now

            result = await self._put_with_retry(
                client, repo_path, file_bytes, existing_sha
            )

        return result

    # ── Path helpers ───────────────────────────────────────────────────────

    def _build_path(self, filename: str, custom_folder: str | None) -> str:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        folder = custom_folder.strip("/") if custom_folder else today
        base = self._cfg.upload_base_path
        return str(PurePosixPath(base) / folder / self._sanitise(filename))

    @staticmethod
    def _sanitise(filename: str) -> str:
        """Remove characters that GitHub paths dislike."""
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", filename)
        return name or "unnamed_file"

    async def _next_free_path(
        self, client: httpx.AsyncClient, original_path: str
    ) -> str:
        """
        Find the next available versioned path, e.g.
        uploads/2024-01-15/photo.jpg → uploads/2024-01-15/photo_1.jpg
        """
        p = PurePosixPath(original_path)
        stem, suffix = p.stem, p.suffix
        counter = 1
        while True:
            candidate = str(p.parent / f"{stem}_{counter}{suffix}")
            sha = await self._get_existing_sha(client, candidate)
            if sha is None:
                return candidate
            counter += 1
            if counter > 999:
                raise GitHubError("Could not find a free filename after 999 attempts.")

    # ── GitHub API calls ───────────────────────────────────────────────────

    async def _get_existing_sha(
        self, client: httpx.AsyncClient, path: str
    ) -> str | None:
        """
        Return the blob SHA of an existing file, or None if it doesn't exist.
        Required by GitHub when overwriting a file.
        """
        url = f"{self._cfg.repo_contents_url}/{path}"
        params = {"ref": self._cfg.github_branch}
        try:
            resp = await client.get(url, headers=self._headers, params=params)
            self._log_rate_limit(resp)
            if resp.status_code == 200:
                return resp.json().get("sha")
            if resp.status_code == 404:
                return None
            self._raise_for_status(resp)
        except httpx.RequestError as exc:
            logger.error("Network error checking existing file: %s", exc)
        return None

    async def _put_with_retry(
        self,
        client: httpx.AsyncClient,
        path: str,
        file_bytes: bytes,
        existing_sha: str | None,
    ) -> UploadResult:
        """
        PUT the file content to GitHub with exponential back-off.
        """
        url = f"{self._cfg.repo_contents_url}/{path}"
        encoded = base64.b64encode(file_bytes).decode()
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        filename = PurePosixPath(path).name

        body: dict = {
            "message": f"📤 آپلود فایل: {filename} — {now_utc}",
            "content": encoded,
            "branch": self._cfg.github_branch,
        }
        if existing_sha:
            body["sha"] = existing_sha

        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await client.put(url, headers=self._headers, json=body)
                self._log_rate_limit(resp)

                if resp.status_code in (200, 201):
                    data = resp.json()
                    commit_sha: str = data["commit"]["sha"]
                    content_data: dict = data["content"]
                    html_url: str = content_data["html_url"]
                    raw_url: str = (
                        f"https://raw.githubusercontent.com/"
                        f"{self._cfg.github_owner}/{self._cfg.github_repo}/"
                        f"{self._cfg.github_branch}/{path}"
                    )
                    logger.info("Uploaded '%s' → commit %s", path, commit_sha[:8])
                    return UploadResult(
                        path=path,
                        sha=commit_sha,
                        html_url=html_url,
                        raw_url=raw_url,
                        size_bytes=len(file_bytes),
                        was_overwrite=existing_sha is not None,
                    )

                # Secondary rate limit → back off and retry
                if resp.status_code == 403 and "secondary rate limit" in resp.text.lower():
                    wait = self._backoff(attempt)
                    logger.warning(
                        "Secondary rate limit hit (attempt %d/%d). Waiting %.1fs …",
                        attempt + 1,
                        _MAX_RETRIES,
                        wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                # Primary rate limit
                if resp.status_code == 403 and "rate limit exceeded" in resp.text.lower():
                    raise RateLimitError(
                        "محدودیت نرخ GitHub فعال شد. لطفاً بعداً دوباره امتحان کنید."
                    )

                self._raise_for_status(resp)

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                wait = self._backoff(attempt)
                logger.warning(
                    "Network error on attempt %d/%d: %s – retrying in %.1fs",
                    attempt + 1,
                    _MAX_RETRIES,
                    exc,
                    wait,
                )
                last_exc = exc
                await asyncio.sleep(wait)

        raise GitHubError(
            f"آپلود پس از {_MAX_RETRIES} تلاش ناموفق بود."
        ) from last_exc

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _backoff(attempt: int) -> float:
        """Exponential back-off with ±20 % jitter."""
        return _BASE_BACKOFF * (2 ** attempt) * (0.8 + 0.4 * random.random())

    def _log_rate_limit(self, resp: httpx.Response) -> None:
        remaining = resp.headers.get("x-ratelimit-remaining")
        limit = resp.headers.get("x-ratelimit-limit")
        if remaining is not None:
            remaining_int = int(remaining)
            if remaining_int < 100:
                logger.warning(
                    "GitHub rate limit low: %s/%s requests remaining.", remaining, limit
                )
            else:
                logger.debug("GitHub rate limit: %s/%s remaining.", remaining, limit)

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        code = resp.status_code
        try:
            msg = resp.json().get("message", resp.text)
        except Exception:
            msg = resp.text

        if code == 401:
            raise AuthError(f"توکن GitHub نامعتبر است یا منقضی شده: {msg}")
        if code == 403:
            raise PermissionError(f"دسترسی رد شد. توکن دارای مجوز کافی نیست: {msg}")
        if code == 404:
            raise GitHubError(
                f"مخزن یا مسیر پیدا نشد. لطفاً GITHUB_OWNER / GITHUB_REPO را بررسی کنید: {msg}"
            )
        if code == 422:
            raise GitHubError(f"داده نامعتبر ارسال شد به GitHub: {msg}")
        raise GitHubError(f"خطای GitHub (HTTP {code}): {msg}")
