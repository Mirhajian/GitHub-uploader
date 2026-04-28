"""
bot/services/github_service.py
────────────────────────────────
All communication with GitHub:

  • Small files  (< lfs_threshold)  → Contents API  (base64 PUT)
  • Large files  (≥ lfs_threshold)  → Git LFS batch + object PUT

Error hierarchy
───────────────
GitHubError          — base for all GitHub-related failures
  AuthError          — 401 Unauthorized
  PermissionError    — 403 Forbidden
  RateLimitError     — 429 / X-RateLimit-Remaining: 0
  FileTooLargeError  — file exceeds hard limits
  LFSNotEnabledError — LFS batch returns 404 / not-found
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

import httpx

from bot.config.settings import get_settings

logger = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────────────────

class GitHubError(Exception):
    """Base exception for all GitHub service errors."""


class AuthError(GitHubError):
    """401 — bad or expired token."""


class PermissionError(GitHubError):
    """403 — token lacks required scope or repo access."""


class RateLimitError(GitHubError):
    """429 or rate-limit headers indicate quota exhausted."""


class FileTooLargeError(GitHubError):
    """File exceeds the maximum size for the chosen upload path."""


class LFSNotEnabledError(GitHubError):
    """LFS batch endpoint returned 404 — LFS not initialised on this repo."""


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class UploadResult:
    path: str           # repo-relative path where file was stored
    sha: str            # git commit SHA (or LFS OID for LFS uploads)
    html_url: str       # link to view on github.com
    raw_url: str        # direct download URL
    was_overwrite: bool # True if an existing file was replaced
    used_lfs: bool      # True if stored via Git LFS


# ── Service ───────────────────────────────────────────────────────────────────

# Timeout profile:
#   connect / pool  — short (30 s); server should respond promptly
#   read / write    — long (600 s); large LFS uploads can be slow on cheap VPS
_TIMEOUT = httpx.Timeout(connect=30.0, read=600.0, write=600.0, pool=30.0)

# Contents API hard limit (GitHub enforces this server-side too)
_CONTENTS_API_MAX_BYTES = 100 * 1024 * 1024   # 100 MB
# LFS hard limit for free accounts
_LFS_MAX_BYTES = 2 * 1024 * 1024 * 1024       # 2 GB

# Chunk size used when streaming a file body to the LFS storage endpoint.
# 4 MB keeps memory pressure low and gives httpx small pieces to send so
# a single network hiccup doesn't abort the whole transfer.
_LFS_CHUNK_BYTES = 4 * 1024 * 1024            # 4 MB


class GitHubService:
    """Async service that uploads files to a GitHub repository."""

    def __init__(self) -> None:
        self._cfg = get_settings()

    # ── Public entry point ────────────────────────────────────────────────

    async def upload_file(
        self,
        file_bytes: bytes,
        original_filename: str,
        custom_folder: Optional[str] = None,
    ) -> UploadResult:
        """
        Upload *file_bytes* to GitHub and return an :class:`UploadResult`.

        Routing:
          • len(file_bytes) <  lfs_threshold  →  Contents API
          • len(file_bytes) >= lfs_threshold  →  Git LFS
        """
        cfg = self._cfg
        size = len(file_bytes)

        # Absolute upper bound — reject before any network call
        if size > _LFS_MAX_BYTES:
            raise FileTooLargeError(
                f"فایل ({size / 1_048_576:.0f} MB) از حداکثر ۲ گیگابایت بیشتر است."
            )

        repo_path = self._build_repo_path(original_filename, custom_folder)

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            if size >= cfg.lfs_threshold_bytes:
                logger.info(
                    "File '%s' (%d bytes) → Git LFS path '%s'",
                    original_filename, size, repo_path,
                )
                return await self._upload_lfs(client, repo_path, file_bytes)
            else:
                if size > _CONTENTS_API_MAX_BYTES:
                    raise FileTooLargeError(
                        f"فایل ({size / 1_048_576:.0f} MB) از ۱۰۰ MB بیشتر است. "
                        "LFS_THRESHOLD_MB را کاهش دهید تا از Git LFS استفاده شود."
                    )
                logger.info(
                    "File '%s' (%d bytes) → Contents API path '%s'",
                    original_filename, size, repo_path,
                )
                return await self._upload_contents_api(client, repo_path, file_bytes)

    # ── Path helpers ──────────────────────────────────────────────────────

    def _build_repo_path(
        self,
        filename: str,
        custom_folder: Optional[str],
    ) -> str:
        cfg = self._cfg
        if custom_folder:
            folder = f"{cfg.upload_base_path}/{custom_folder.strip('/')}"
        else:
            folder = f"{cfg.upload_base_path}/{date.today().isoformat()}"
        safe_name = self._sanitise_filename(filename)
        return f"{folder}/{safe_name}"

    @staticmethod
    def _sanitise_filename(name: str) -> str:
        """Replace characters that are problematic in GitHub paths."""
        name = name.strip()
        name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
        return name or "unnamed_file"

    # ── Contents API upload ───────────────────────────────────────────────

    async def _upload_contents_api(
        self,
        client: httpx.AsyncClient,
        repo_path: str,
        file_bytes: bytes,
    ) -> UploadResult:
        cfg = self._cfg
        url = f"{cfg.repo_contents_url}/{repo_path}"
        headers = self._github_headers()

        # Check if the file already exists (need its SHA to overwrite)
        existing_sha: Optional[str] = None
        get_resp = await self._request_with_retry(client, "GET", url, headers=headers)
        if get_resp.status_code == 200:
            existing_sha = get_resp.json().get("sha")
        elif get_resp.status_code not in (404,):
            self._raise_for_status(get_resp)

        # Resolve conflict strategy
        was_overwrite = False
        if existing_sha:
            if cfg.file_conflict_strategy == "overwrite":
                was_overwrite = True
            else:
                repo_path = await self._next_versioned_path(
                    client, repo_path, headers
                )
                url = f"{cfg.repo_contents_url}/{repo_path}"
                existing_sha = None

        # Build payload
        payload: dict = {
            "message": f"upload: {repo_path}",
            "content": base64.b64encode(file_bytes).decode(),
            "branch": cfg.github_branch,
        }
        if existing_sha:
            payload["sha"] = existing_sha

        put_resp = await self._request_with_retry(
            client, "PUT", url, headers=headers, json=payload
        )
        self._raise_for_status(put_resp)
        data = put_resp.json()

        commit_sha = data["commit"]["sha"]
        content_data = data.get("content", {})
        html_url = content_data.get(
            "html_url",
            f"https://github.com/{cfg.github_owner}/{cfg.github_repo}/blob/{cfg.github_branch}/{repo_path}",
        )
        raw_url = (
            f"https://raw.githubusercontent.com/{cfg.github_owner}"
            f"/{cfg.github_repo}/{cfg.github_branch}/{repo_path}"
        )

        return UploadResult(
            path=repo_path,
            sha=commit_sha,
            html_url=html_url,
            raw_url=raw_url,
            was_overwrite=was_overwrite,
            used_lfs=False,
        )

    async def _next_versioned_path(
        self,
        client: httpx.AsyncClient,
        original_path: str,
        headers: dict,
    ) -> str:
        """Return the next free versioned path, e.g. file_1.ext, file_2.ext …"""
        # Split path into stem + extension
        if "." in original_path.rsplit("/", 1)[-1]:
            dot_idx = original_path.rfind(".")
            stem = original_path[:dot_idx]
            ext = original_path[dot_idx:]
        else:
            stem = original_path
            ext = ""

        cfg = self._cfg
        for n in range(1, 10_000):
            candidate = f"{stem}_{n}{ext}"
            check_url = f"{cfg.repo_contents_url}/{candidate}"
            resp = await self._request_with_retry(
                client, "GET", check_url, headers=headers
            )
            if resp.status_code == 404:
                return candidate
        raise GitHubError("تعداد زیادی نسخه از این فایل وجود دارد.")

    # ── Git LFS upload ────────────────────────────────────────────────────

    async def _upload_lfs(
        self,
        client: httpx.AsyncClient,
        repo_path: str,
        file_bytes: bytes,
    ) -> UploadResult:
        cfg = self._cfg
        oid = hashlib.sha256(file_bytes).hexdigest()
        size = len(file_bytes)

        # 1. LFS Batch API — ask GitHub for an upload URL
        upload_url, upload_headers = await self._lfs_batch(
            client, oid, size
        )

        # 2. PUT the object to the storage URL (Netlify / Azure / S3)
        if upload_url:
            await self._lfs_put_object(client, upload_url, upload_headers, file_bytes, oid)
        else:
            logger.info("LFS object %s already exists on remote — skipping PUT.", oid[:10])

        # 3. Commit a pointer file via Contents API
        return await self._lfs_commit_pointer(client, repo_path, oid, size)

    async def _lfs_batch(
        self,
        client: httpx.AsyncClient,
        oid: str,
        size: int,
    ) -> tuple[Optional[str], dict]:
        """
        Call the LFS Batch API.
        Returns (upload_url, extra_headers) or (None, {}) if already uploaded.
        """
        cfg = self._cfg
        url = (
            f"https://github.com/{cfg.github_owner}/{cfg.github_repo}"
            ".git/info/lfs/objects/batch"
        )
        headers = {
            "Accept": "application/vnd.git-lfs+json",
            "Content-Type": "application/vnd.git-lfs+json",
            "Authorization": f"token {cfg.github_token}",
        }
        payload = {
            "operation": "upload",
            "transfers": ["basic"],
            "objects": [{"oid": oid, "size": size}],
        }

        resp = await self._request_with_retry(
            client, "POST", url, headers=headers, json=payload
        )

        if resp.status_code == 404:
            raise LFSNotEnabledError(
                "Git LFS روی این مخزن فعال نیست.\n"
                "لطفاً ابتدا `git lfs install` را در مخزن اجرا کنید و "
                "فایل `.gitattributes` را push کنید."
            )
        self._raise_for_status(resp)

        objects = resp.json().get("objects", [])
        if not objects:
            raise GitHubError("پاسخ LFS Batch خالی بود.")

        obj = objects[0]
        if "error" in obj:
            raise GitHubError(f"LFS Batch error: {obj['error']}")

        actions = obj.get("actions", {})
        upload_action = actions.get("upload")
        if not upload_action:
            # Object already exists on LFS storage
            return None, {}

        upload_url: str = upload_action["href"]
        extra_headers: dict = upload_action.get("header", {})
        return upload_url, extra_headers

    async def _lfs_put_object(
        self,
        client: httpx.AsyncClient,
        upload_url: str,
        extra_headers: dict,
        file_bytes: bytes,
        oid: str,
    ) -> None:
        """
        Stream *file_bytes* to the LFS storage endpoint.

        Key fixes vs. the original implementation:
          1. Long read/write timeout (inherited from the shared AsyncClient
             which was created with _TIMEOUT).
          2. Async generator streams data in 4 MB chunks instead of sending
             the entire buffer at once — avoids httpx buffering the whole
             file in memory and reduces the chance of a mid-transfer
             ReadError on slow/flaky connections.
          3. Up to 3 retry attempts with exponential back-off on transient
             network errors (ReadError, WriteError, ConnectError).
        """
        headers = {
            "Content-Type": "application/octet-stream",
            "Content-Length": str(len(file_bytes)),
            **extra_headers,
        }

        async def _stream():
            for offset in range(0, len(file_bytes), _LFS_CHUNK_BYTES):
                yield file_bytes[offset: offset + _LFS_CHUNK_BYTES]

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(
                    "LFS PUT attempt %d/%d — OID %s… (%d bytes)",
                    attempt, max_attempts, oid[:10], len(file_bytes),
                )
                resp = await client.put(
                    upload_url,
                    headers=headers,
                    content=_stream(),
                )
                if resp.status_code not in (200, 201):
                    raise GitHubError(
                        f"LFS PUT failed (HTTP {resp.status_code}): "
                        f"{resp.text[:300]}"
                    )
                logger.info("LFS PUT succeeded (OID %s…).", oid[:10])
                return

            except (httpx.ReadError, httpx.WriteError, httpx.ConnectError) as exc:
                if attempt == max_attempts:
                    raise GitHubError(
                        f"آپلود LFS پس از {max_attempts} تلاش ناموفق بود: {exc}"
                    ) from exc
                wait = 2 ** attempt  # 2 s, 4 s
                logger.warning(
                    "LFS PUT attempt %d/%d failed (%s: %s) — retrying in %d s…",
                    attempt, max_attempts, type(exc).__name__, exc, wait,
                )
                await asyncio.sleep(wait)

    async def _lfs_commit_pointer(
        self,
        client: httpx.AsyncClient,
        repo_path: str,
        oid: str,
        size: int,
    ) -> UploadResult:
        """Commit an LFS pointer file to the repository via Contents API."""
        cfg = self._cfg

        pointer_content = (
            "version https://git-lfs.github.com/spec/v1\n"
            f"oid sha256:{oid}\n"
            f"size {size}\n"
        )
        pointer_bytes = pointer_content.encode()

        url = f"{cfg.repo_contents_url}/{repo_path}"
        headers = self._github_headers()

        # Check for an existing pointer (overwrite / version strategy)
        existing_sha: Optional[str] = None
        was_overwrite = False
        get_resp = await self._request_with_retry(client, "GET", url, headers=headers)
        if get_resp.status_code == 200:
            existing_sha = get_resp.json().get("sha")
            if cfg.file_conflict_strategy == "overwrite":
                was_overwrite = True
            else:
                repo_path = await self._next_versioned_path(
                    client, repo_path, headers
                )
                url = f"{cfg.repo_contents_url}/{repo_path}"
                existing_sha = None
        elif get_resp.status_code not in (404,):
            self._raise_for_status(get_resp)

        payload: dict = {
            "message": f"upload (lfs): {repo_path}",
            "content": base64.b64encode(pointer_bytes).decode(),
            "branch": cfg.github_branch,
        }
        if existing_sha:
            payload["sha"] = existing_sha

        put_resp = await self._request_with_retry(
            client, "PUT", url, headers=headers, json=payload
        )
        self._raise_for_status(put_resp)
        data = put_resp.json()

        commit_sha = data["commit"]["sha"]
        html_url = (
            f"https://github.com/{cfg.github_owner}/{cfg.github_repo}"
            f"/blob/{cfg.github_branch}/{repo_path}"
        )
        raw_url = (
            f"https://media.githubusercontent.com/media/{cfg.github_owner}"
            f"/{cfg.github_repo}/{cfg.github_branch}/{repo_path}"
        )

        return UploadResult(
            path=repo_path,
            sha=commit_sha,
            html_url=html_url,
            raw_url=raw_url,
            was_overwrite=was_overwrite,
            used_lfs=True,
        )

    # ── Cleanup (oldest-first deletion) ───────────────────────────────────

    async def maybe_cleanup(self) -> None:
        """
        If cleanup is enabled and repo size exceeds the cap, delete the
        oldest uploaded files until we are under the threshold.
        Called from the upload handler after a successful upload.
        """
        cfg = self._cfg
        if not cfg.cleanup_enabled:
            return

        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            headers = self._github_headers()
            files = await self._list_uploaded_files(client, headers)
            if not files:
                return

            total_bytes = sum(f["size"] for f in files)
            max_bytes = cfg.cleanup_max_repo_mb * 1024 * 1024

            if total_bytes <= max_bytes:
                return

            logger.info(
                "Repo size %.1f MB > limit %.1f MB — running cleanup.",
                total_bytes / 1_048_576,
                cfg.cleanup_max_repo_mb,
            )

            # Sort oldest-first; keep the N newest untouched
            files_sorted = sorted(files, key=lambda f: f.get("path", ""))
            deletable = files_sorted[: max(0, len(files_sorted) - cfg.cleanup_keep_latest)]

            for f in deletable:
                if total_bytes <= max_bytes:
                    break
                await self._delete_file(client, f, headers)
                total_bytes -= f["size"]

    async def _list_uploaded_files(
        self,
        client: httpx.AsyncClient,
        headers: dict,
    ) -> list[dict]:
        cfg = self._cfg
        url = f"{cfg.repo_contents_url}/{cfg.upload_base_path}"
        resp = await self._request_with_retry(client, "GET", url, headers=headers)
        if resp.status_code == 404:
            return []
        self._raise_for_status(resp)
        return [
            item for item in resp.json()
            if item.get("type") == "file"
        ]

    async def _delete_file(
        self,
        client: httpx.AsyncClient,
        file_info: dict,
        headers: dict,
    ) -> None:
        cfg = self._cfg
        url = f"{cfg.repo_contents_url}/{file_info['path']}"
        payload = {
            "message": f"cleanup: remove {file_info['path']}",
            "sha": file_info["sha"],
            "branch": cfg.github_branch,
        }
        resp = await self._request_with_retry(
            client, "DELETE", url, headers=headers, json=payload
        )
        if resp.status_code in (200, 204):
            logger.info("Deleted old file: %s", file_info["path"])
        else:
            logger.warning(
                "Failed to delete %s (HTTP %d)", file_info["path"], resp.status_code
            )

    # ── HTTP helpers ──────────────────────────────────────────────────────

    def _github_headers(self) -> dict:
        return {
            "Authorization": f"token {self._cfg.github_token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _request_with_retry(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        max_attempts: int = 3,
        **kwargs,
    ) -> httpx.Response:
        """
        Execute an HTTP request with exponential back-off retries.

        Retries on:
          • 429 Too Many Requests (honours Retry-After header if present)
          • 500 / 502 / 503 / 504 server errors
          • httpx transport-level errors (ReadError, ConnectError, …)
        """
        last_exc: Optional[Exception] = None

        for attempt in range(1, max_attempts + 1):
            try:
                resp = await client.request(method, url, **kwargs)

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", "60"))
                    logger.warning(
                        "GitHub rate-limited (429) — waiting %d s (attempt %d/%d).",
                        retry_after, attempt, max_attempts,
                    )
                    if attempt < max_attempts:
                        await asyncio.sleep(retry_after)
                        continue
                    raise RateLimitError(
                        f"محدودیت نرخ GitHub. لطفاً {retry_after} ثانیه صبر کنید."
                    )

                if resp.status_code in (500, 502, 503, 504) and attempt < max_attempts:
                    wait = 2 ** attempt
                    logger.warning(
                        "GitHub server error %d — retrying in %d s (attempt %d/%d).",
                        resp.status_code, wait, attempt, max_attempts,
                    )
                    await asyncio.sleep(wait)
                    continue

                return resp

            except (httpx.ReadError, httpx.WriteError, httpx.ConnectError,
                    httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt == max_attempts:
                    raise GitHubError(
                        f"خطای شبکه پس از {max_attempts} تلاش: {type(exc).__name__}: {exc}"
                    ) from exc
                wait = 2 ** attempt
                logger.warning(
                    "Network error on %s %s (%s) — retrying in %d s (attempt %d/%d).",
                    method, url, exc, wait, attempt, max_attempts,
                )
                await asyncio.sleep(wait)

        # Should never reach here
        raise GitHubError(f"درخواست پس از {max_attempts} تلاش ناموفق بود.") from last_exc

    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        """Map HTTP error codes to typed exceptions."""
        if resp.status_code < 400:
            return
        if resp.status_code == 401:
            raise AuthError(
                "توکن GitHub نامعتبر یا منقضی شده است (401). "
                "لطفاً GITHUB_TOKEN را بررسی کنید."
            )
        if resp.status_code == 403:
            raise PermissionError(
                "دسترسی رد شد (403). مطمئن شوید توکن دارای دسترسی repo است."
            )
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After", "کمی")
            raise RateLimitError(
                f"محدودیت نرخ GitHub. لطفاً {retry_after} ثانیه صبر کنید."
            )
        try:
            message = resp.json().get("message", resp.text[:200])
        except Exception:
            message = resp.text[:200]
        raise GitHubError(f"خطای GitHub (HTTP {resp.status_code}): {message}")
