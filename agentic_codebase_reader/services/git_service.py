"""
services/git_service.py
~~~~~~~~~~~~~~~~~~~~~~~
Infrastructure service for Git operations.
"""
from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import httpx
from git import GitCommandError, InvalidGitRepositoryError, Repo

from agentic_codebase_reader.config import settings

logger = logging.getLogger(__name__)


class GitServiceError(Exception):
    """Raised for any Git-service-level failure."""


class GitService:
    """Handles all Git operations required by the pipeline."""

    # ── URL validation ────────────────────────────────────────────────────────

    def validate_url(self, repo_url: str) -> bool:
        """Check that a GitHub URL is syntactically valid and publicly reachable.

        Args:
            repo_url: A GitHub repository URL.

        Returns:
            ``True`` if the repository appears to be accessible.

        Raises:
            ValueError: If ``repo_url`` is not a valid HTTPS GitHub URL.
        """
        parsed = urlparse(repo_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"URL must use http/https scheme: {repo_url!r}")
        if "github.com" not in (parsed.netloc or ""):
            raise ValueError(f"URL must be a GitHub URL: {repo_url!r}")

        parts = parsed.path.strip("/").split("/")
        if len(parts) < 2 or not all(parts[:2]):
            raise ValueError(
                f"URL must contain <owner>/<repo>: {repo_url!r}"
            )

        try:
            with httpx.Client(follow_redirects=True, timeout=10) as client:
                resp = client.head(repo_url)
            if resp.status_code == 404:
                raise GitServiceError(
                    f"Repository not found (404): {repo_url}"
                )
            return resp.status_code < 400
        except httpx.RequestError as exc:
            raise GitServiceError(
                f"Could not reach {repo_url!r}: {exc}"
            ) from exc

    # ── Cloning ───────────────────────────────────────────────────────────────

    def clone(self, repo_url: str, target_dir: Path | None = None) -> Path:
        """Clone a public GitHub repository to a local directory.

        Args:
            repo_url:   A public GitHub repository URL.
            target_dir: Optional existing directory to clone into.

        Returns:
            Absolute path to the cloned repository root.

        Raises:
            GitServiceError: If the ``git clone`` command fails.
        """
        if target_dir is None:
            tmp_root = settings.clone_tmp_dir or Path(tempfile.gettempdir())
            target_dir = Path(
                tempfile.mkdtemp(prefix="codebase_reader_", dir=tmp_root)
            )
        else:
            target_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Cloning %s → %s", repo_url, target_dir)
        try:
            Repo.clone_from(
                repo_url,
                str(target_dir),
                depth=1,          # shallow clone — faster
                single_branch=True,
            )
        except GitCommandError as exc:
            raise GitServiceError(
                f"git clone failed for {repo_url!r}: {exc}"
            ) from exc

        return target_dir.resolve()

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self, clone_path: Path) -> None:
        """Remove a cloned repository from disk.

        Args:
            clone_path: Path returned by a previous :meth:`clone` call.
        """
        if clone_path.exists():
            shutil.rmtree(clone_path, ignore_errors=True)
            logger.debug("Cleaned up clone at %s", clone_path)

    # ── Size estimation ───────────────────────────────────────────────────────

    def get_repo_size_mb(self, repo_url: str) -> float:
        """Estimate the repository size in MB via the GitHub API.

        Args:
            repo_url: A GitHub repository URL.

        Returns:
            Estimated size in MB.

        Raises:
            GitServiceError: If the repository metadata cannot be retrieved.
        """
        parsed = urlparse(repo_url)
        parts = parsed.path.strip("/").split("/")
        if len(parts) < 2:
            raise GitServiceError(f"Cannot parse owner/repo from: {repo_url!r}")

        owner, repo = parts[0], parts[1]
        api_url = f"https://api.github.com/repos/{owner}/{repo}"

        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    api_url,
                    headers={"Accept": "application/vnd.github+json"},
                )
            resp.raise_for_status()
            size_kb: int = resp.json().get("size", 0)
            return round(size_kb / 1024, 2)
        except httpx.HTTPStatusError as exc:
            raise GitServiceError(
                f"GitHub API returned {exc.response.status_code} for {api_url}"
            ) from exc
        except httpx.RequestError as exc:
            raise GitServiceError(
                f"Could not reach GitHub API: {exc}"
            ) from exc

    # ── Helper ────────────────────────────────────────────────────────────────

    @staticmethod
    def extract_repo_name(repo_url: str) -> str:
        """Parse a GitHub URL and return the repository name.

        Args:
            repo_url: A GitHub repository URL.

        Returns:
            The repository name string (without .git suffix).

        Raises:
            ValueError: If the URL cannot be parsed.
        """
        path = urlparse(repo_url).path.strip("/")
        parts = path.split("/")
        if len(parts) < 2 or not parts[1]:
            raise ValueError(f"Cannot extract repo name from: {repo_url!r}")
        return parts[1].removesuffix(".git")
