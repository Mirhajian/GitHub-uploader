"""
bot/services/github_service.py
──────────────────────────────
All interaction with GitHub happens here: Contents API for small files,
Git LFS Batch API for large ones, and the Trees/Commits API for cleanup.

Routing logic
─────────────
• file size < LFS_THRESHOLD_MB  → GitHub Contents API  (simple base64 PUT)
• file size >= LFS_THRESHOLD_MB → Git LFS Batch API    (upload to LFS storage)

Git LFS upload flow (3 steps)
──────────────────────────────
1. POST /repos/{owner}/{repo}/info/lfs/objects/batch  — request an upload URL
2. PUT  <upload_url>                                   — push raw bytes
3. POST /repos/{owner}/{repo}/git/commits             — commit a pointer file
   (pointer text file referencing the LFS OID + size)

Other behaviours
────────────────
• Async HTTP via httpx.AsyncClient
• Exponential back-off with jitter on secondary rate limits
• Respects x-ratelimit-remaining header (warning at < 100)
• Duplicate filenames: overwrite (fetch SHA) or version (_1, _2, …)
• Cleanup: when enabled, deletes oldest files via the Contents API once
  the repo's upload folder exceeds CLEANUP_MAX_REPO_MB, always keeping
  the CLEANUP_KEEP_LATEST most recent files untouched.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import random
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePosixPath

import httpx

from bot.config.settings import get_settings

logger = logging.getLogger(__name__)

# Contents API hard limit — anything at or above goes through LFS.
GITHUB_CONTENTS_MAX_BYTES = 100 * 1024 * 1024  # 100 MB

_MAX_RETRIES = 5
_BASE_BACKOFF = 1.0  # seconds


# ── Custom exceptions ──────────────────────────────────────────────────────────


class GitHubError(Exception):
    """Base class for GitHub service errors."""


class FileTooLargeError(GitHubError):
    """File exceeds limits even for LFS (>= 2 GB free tier cap)."""


class RateLimitError(GitHubError):
    """GitHub primary rate limit exceeded."""


class AuthError(GitHubError):
    """Invalid or expired GitHub token."""


class PermissionError(GitHubError):
    """Token lacks required permissions."""


class LFSNotEnabledError(GitHubError):
    """Repository does not have Git LFS enabled."""


# ── Result dataclass ───────────────────────────────────────────────────────────


@dataclass
class UploadResult:
    path: str           # path inside the repo, e.g. uploads/2024-01-15/photo.jpg
    sha: str            # commit SHA
    html_url: str       # GitHub blob/LFS URL
    raw_url: str        # direct download URL
    size_bytes: int
    was_overwrite: bool
    used_lfs: bool      # True when the file was stored via Git LFS


# ── Service ────────────────────────────────────────────────────────────────────


class GitHubService:
    """Async wrapper around GitHub Contents API + Git LFS Batch API."""

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

        Automatically routes to Git LFS when the file is >= LFS_THRESHOLD_MB.
        After a successful upload, triggers cleanup if enabled.
        """
        size = len(file_bytes)
        repo_path = self._build_path(original_filename, custom_folder)

        async with httpx.AsyncClient(timeout=120.0) as client:
            if size >= self._cfg.lfs_threshold_bytes:
                result = await self._upload_lfs(client, repo_path, file_bytes)
            else:
                result = await self._upload_contents(client, repo_path, file_bytes)

        # Non-blocking cleanup — run after replying to user
        if self._cfg.cleanup_enabled:
            asyncio.create_task(self._cleanup_old_files())

        return result

    # ── Contents API path (< LFS threshold) ────────────────────────────────

    async def _upload_contents(
        self,
        client: httpx.AsyncClient,
        repo_path: str,
        file_bytes: bytes,
    ) -> UploadResult:
        existing_sha = await self._get_existing_sha(client, repo_path)

        if existing_sha and self._cfg.file_conflict_strategy == "version":
            repo_path = await self._next_free_path(client, repo_path)
            existing_sha = None

        return await self._put_with_retry(client, repo_path, file_bytes, existing_sha)

    # ── Git LFS path (>= LFS threshold) ────────────────────────────────────

    async def _upload_lfs(
        self,
        client: httpx.AsyncClient,
        repo_path: str,
        file_bytes: bytes,
    ) -> UploadResult:
        """
        Full Git LFS upload flow:
          1. Request upload URL from LFS Batch API
          2. PUT raw bytes to the storage URL
          3. Commit an LFS pointer file into the repo
        """
        size = len(file_bytes)
        oid = hashlib.sha256(file_bytes).hexdigest()

        logger.info(
            "Routing '%s' (%.1f MB) through Git LFS (oid=%s…)",
            repo_path,
            size / 1_048_576,
            oid[:12],
        )

        # ── Step 1: request upload URL ──────────────────────────────────
        upload_url, verify_url, verify_header = await self._lfs_batch_upload(
            client, oid, size
        )

        # ── Step 2: PUT raw bytes ───────────────────────────────────────
        if upload_url:
            await self._lfs_put_object(client, upload_url, file_bytes, oid)
            if verify_url:
                await self._lfs_verify(client, verify_url, verify_header, oid, size)
        else:
            logger.info("LFS object already exists on server (oid=%s…), skipping upload.", oid[:12])

        # ── Step 3: commit the pointer file ────────────────────────────
        pointer_text = self._lfs_pointer(oid, size)

        # Handle conflict strategy for the pointer path
        existing_sha = await self._get_existing_sha(client, repo_path)
        if existing_sha and self._cfg.file_conflict_strategy == "version":
            repo_path = await self._next_free_path(client, repo_path)
            existing_sha = None

        commit_sha = await self._commit_lfs_pointer(
            client, repo_path, pointer_text, existing_sha
        )

        html_url = (
            f"https://github.com/{self._cfg.github_owner}/{self._cfg.github_repo}"
            f"/blob/{self._cfg.github_branch}/{repo_path}"
        )
        # LFS raw download goes through media.githubusercontent.com
        raw_url = (
            f"https://media.githubusercontent.com/media/"
            f"{self._cfg.github_owner}/{self._cfg.github_repo}/"
            f"{self._cfg.github_branch}/{repo_path}"
        )

        return UploadResult(
            path=repo_path,
            sha=commit_sha,
            html_url=html_url,
            raw_url=raw_url,
            size_bytes=size,
            was_overwrite=existing_sha is not None,
            used_lfs=True,
        )

    async def _lfs_batch_upload(
        self,
        client: httpx.AsyncClient,
        oid: str,
        size: int,
    ) -> tuple[str | None, str | None, dict | None]:
        """
        Call the LFS Batch API and return (upload_url, verify_url, verify_header).
        upload_url is None if the object already exists on the server.
        """
        url = (
            f"https://github.com/{self._cfg.github_owner}/"
            f"{self._cfg.github_repo}.git/info/lfs/objects/batch"
        )
        headers = {
            "Authorization": f"Bearer {self._cfg.github_token}",
            "Accept": "application/vnd.git-lfs+json",
            "Content-Type": "application/vnd.git-lfs+json",
        }
        payload = {
            "operation": "upload",
            "transfers": ["basic"],
            "objects": [{"oid": oid, "size": size}],
            "ref": {"name": f"refs/heads/{self._cfg.github_branch}"},
        }

        for attempt in range(_MAX_RETRIES):
            try:
                resp = await client.post(url, headers=headers, json=payload)
                if resp.status_code == 404:
                    raise LFSNotEnabledError(
                        "Git LFS به نظر می‌رسد در این مخزن فعال نیست.\n"
                        "لطفاً ابتدا `git lfs install` و `git lfs track` را اجرا کنید "
                        "و یک فایل .gitattributes کامیت کنید."
                    )
                if resp.status_code == 401:
                    raise AuthError("توکن GitHub برای دسترسی به LFS نامعتبر است.")
                resp.raise_for_status()

                obj = resp.json()["objects"][0]
                if "error" in obj:
                    raise GitHubError(
                        f"خطای LFS Batch API: {obj['error'].get('message', obj['error'])}"
                    )

                actions = obj.get("actions", {})
                if not actions:
                    # Object already exists — no upload needed
                    return None, None, None

                upload_href = actions["upload"]["href"]
                verify_action = actions.get("verify", {})
                verify_href = verify_action.get("href")
                verify_header = verify_action.get("header")
                return upload_href, verify_href, verify_header

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                wait = self._backoff(attempt)
                logger.warning("LFS batch request failed (attempt %d): %s", attempt + 1, exc)
                await asyncio.sleep(wait)

        raise GitHubError("درخواست LFS Batch API پس از چند تلاش ناموفق بود.")

    async def _lfs_put_object(
        self,
        client: httpx.AsyncClient,
        upload_url: str,
        file_bytes: bytes,
        oid: str,
    ) -> None:
        """PUT the raw file bytes to the LFS storage URL."""
        headers = {
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(file_bytes)),
        }
        for attempt in range(_MAX_RETRIES):
            try:
                resp = await client.put(upload_url, headers=headers, content=file_bytes)
                if resp.status_code in (200, 201):
                    logger.info("LFS object uploaded successfully (oid=%s…).", oid[:12])
                    return
                resp.raise_for_status()
            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                wait = self._backoff(attempt)
                logger.warning("LFS PUT failed (attempt %d): %s", attempt + 1, exc)
                await asyncio.sleep(wait)

        raise GitHubError("آپلود LFS پس از چند تلاش ناموفق بود.")

    async def _lfs_verify(
        self,
        client: httpx.AsyncClient,
        verify_url: str,
        verify_header: dict | None,
        oid: str,
        size: int,
    ) -> None:
        headers = {
            "Authorization": f"Bearer {self._cfg.github_token}",
            "Accept": "application/vnd.git-lfs+json",
            "Content-Type": "application/vnd.git-lfs+json",
            **(verify_header or {}),
        }
        try:
            resp = await client.post(verify_url, headers=headers, json={"oid": oid, "size": size})
            if resp.status_code not in (200, 204):
                logger.warning("LFS verify returned %d — continuing anyway.", resp.status_code)
        except Exception as exc:
            logger.warning("LFS verify step failed (non-fatal): %s", exc)

    @staticmethod
    def _lfs_pointer(oid: str, size: int) -> str:
        """Build the Git LFS pointer file content."""
        return (
            "version https://git-lfs.github.com/spec/v1\n"
            f"oid sha256:{oid}\n"
            f"size {size}\n"
        )

    async def _commit_lfs_pointer(
        self,
        client: httpx.AsyncClient,
        repo_path: str,
        pointer_text: str,
        existing_sha: str | None,
    ) -> str:
        """Write the LFS pointer as a regular file via the Contents API and return commit SHA."""
        pointer_bytes = pointer_text.encode()
        result = await self._put_with_retry(
            client, repo_path, pointer_bytes, existing_sha, is_lfs_pointer=True
        )
        return result.sha

    # ── Cleanup ─────────────────────────────────────────────────────────────

    async def _cleanup_old_files(self) -> None:
        """
        Delete the oldest files from the upload base path when total size
        exceeds CLEANUP_MAX_REPO_MB, always keeping the CLEANUP_KEEP_LATEST
        most recent files.

        Uses the GitHub Trees API to list files, sorts by path (date-based
        paths naturally sort chronologically), then deletes via Contents API.
        """
        cfg = self._cfg
        logger.info("Running cleanup check (max %.0f MB, keep latest %d) …",
                    cfg.cleanup_max_repo_mb, cfg.cleanup_keep_latest)

        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                # Fetch the full tree recursively
                tree_url = (
                    f"{cfg.github_api_base}/repos/{cfg.github_owner}/{cfg.github_repo}"
                    f"/git/trees/{cfg.github_branch}?recursive=1"
                )
                resp = await client.get(tree_url, headers=self._headers)
                resp.raise_for_status()
                tree = resp.json().get("tree", [])

                # Filter to files under upload_base_path only, exclude LFS pointers
                upload_files = [
                    item for item in tree
                    if item["type"] == "blob"
                    and item["path"].startswith(cfg.upload_base_path + "/")
                ]

                if not upload_files:
                    logger.info("Cleanup: no uploaded files found.")
                    return

                total_kb = sum(item.get("size", 0) for item in upload_files) / 1024
                total_mb = total_kb / 1024
                logger.info("Cleanup: %.1f MB across %d files.", total_mb, len(upload_files))

                if total_mb <= cfg.cleanup_max_repo_mb:
                    logger.info("Cleanup: under limit (%.1f / %.0f MB), nothing to do.",
                                total_mb, cfg.cleanup_max_repo_mb)
                    return

                # Sort oldest first (path contains date, so lexicographic = chronological)
                upload_files.sort(key=lambda x: x["path"])

                # Determine how many to delete
                keep_count = max(cfg.cleanup_keep_latest, 0)
                deletable = upload_files[:-keep_count] if keep_count else upload_files
                if not deletable:
                    logger.warning("Cleanup: cannot free space — all files are in keep window.")
                    return

                logger.info("Cleanup: deleting %d oldest file(s) …", len(deletable))
                for item in deletable:
                    await self._delete_file(client, item["path"], item["sha"])

            except Exception as exc:
                logger.error("Cleanup failed: %s", exc)

    async def _delete_file(
        self, client: httpx.AsyncClient, path: str, blob_sha: str
    ) -> None:
        url = f"{self._cfg.repo_contents_url}/{path}"
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        body = {
            "message": f"🧹 پاکسازی خودکار: {PurePosixPath(path).name} — {now_utc}",
            "sha": blob_sha,
            "branch": self._cfg.github_branch,
        }
        try:
            resp = await client.delete(url, headers=self._headers, json=body)
            if resp.status_code == 200:
                logger.info("Cleanup: deleted '%s'.", path)
            else:
                logger.warning("Cleanup: could not delete '%s' (HTTP %d).", path, resp.status_code)
        except Exception as exc:
            logger.warning("Cleanup: error deleting '%s': %s", path, exc)

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
        is_lfs_pointer: bool = False,
    ) -> UploadResult:
        url = f"{self._cfg.repo_contents_url}/{path}"
        encoded = base64.b64encode(file_bytes).decode()
        now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        filename = PurePosixPath(path).name
        commit_msg = (
            f"📤 آپلود LFS pointer: {filename} — {now_utc}"
            if is_lfs_pointer
            else f"📤 آپلود فایل: {filename} — {now_utc}"
        )

        body: dict = {
            "message": commit_msg,
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
                        used_lfs=is_lfs_pointer,
                    )

                if resp.status_code == 403 and "secondary rate limit" in resp.text.lower():
                    wait = self._backoff(attempt)
                    logger.warning(
                        "Secondary rate limit (attempt %d/%d). Waiting %.1fs …",
                        attempt + 1, _MAX_RETRIES, wait,
                    )
                    await asyncio.sleep(wait)
                    continue

                if resp.status_code == 403 and "rate limit exceeded" in resp.text.lower():
                    raise RateLimitError(
                        "محدودیت نرخ GitHub فعال شد. لطفاً بعداً دوباره امتحان کنید."
                    )

                self._raise_for_status(resp)

            except (httpx.TimeoutException, httpx.ConnectError) as exc:
                wait = self._backoff(attempt)
                logger.warning(
                    "Network error on attempt %d/%d: %s – retrying in %.1fs",
                    attempt + 1, _MAX_RETRIES, exc, wait,
                )
                last_exc = exc
                await asyncio.sleep(wait)

        raise GitHubError(
            f"آپلود پس از {_MAX_RETRIES} تلاش ناموفق بود."
        ) from last_exc

    # ── Helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _backoff(attempt: int) -> float:
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
