"""
api/routes.py
~~~~~~~~~~~~~
FastAPI route definitions.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from fastapi.responses import FileResponse

from agentic_codebase_reader import __version__
from agentic_codebase_reader.api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    HealthResponse,
)
from agentic_codebase_reader.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """Return the API liveness status and current version."""
    return HealthResponse(version=__version__)


@router.post("/analyze", response_model=AnalyzeResponse, tags=["Pipeline"])
async def analyze_repository(body: AnalyzeRequest) -> AnalyzeResponse:
    """Run the multi-agent documentation pipeline for a GitHub repository.

    Args:
        body: JSON body containing ``repo_url``.

    Returns:
        :class:`AnalyzeResponse` with status, repo name, and output path.
    """
    from agentic_codebase_reader.agents.supervisor import Supervisor
    from agentic_codebase_reader.services.git_service import GitServiceError

    repo_url = str(body.repo_url)
    mode = body.mode
    supervisor = Supervisor()

    try:
        report = await supervisor.run(repo_url, mode=mode)
    except ValueError as exc:
        # Invalid URL / unreachable repo / size guard.
        return AnalyzeResponse(
            repo_name="",
            status="error",
            error=str(exc),
        )
    except (RuntimeError, GitServiceError) as exc:
        logger.exception("Pipeline failed for %s", repo_url)
        return AnalyzeResponse(
            repo_name="",
            status="error",
            error=f"Pipeline error: {exc}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Unexpected error for %s", repo_url)
        return AnalyzeResponse(
            repo_name="",
            status="error",
            error=f"Unexpected error: {exc}",
        )

    return AnalyzeResponse(
        repo_name=report.repo_name,
        status="completed",
        output_path=str(report.output_path) if report.output_path else None,
    )


@router.get("/download/{identifier:path}", tags=["Pipeline"])
async def download_docs(
    identifier: str,
    file: str = Query(default="docs", pattern="^(docs|readme)$"),
) -> FileResponse:
    """Download the generated documentation for a repository.

    Args:
        identifier: Repository name or full GitHub URL.
        file:       Which file to download — ``"docs"`` (default) or ``"readme"``.

    Returns:
        The requested file as a downloadable attachment.

    Raises:
        HTTPException(404): If no docs have been generated for this repo.
    """
    # If the user passed a full URL, extract just the repo_name part —
    # same logic as Supervisor._extract_repo_name so the folder name matches.
    if identifier.startswith("http") or "/" in identifier:
        from urllib.parse import urlparse
        try:
            path_parts = urlparse(identifier).path.strip("/").split("/")
            repo_name = path_parts[1].removesuffix(".git") if len(path_parts) >= 2 else identifier
        except (IndexError, ValueError):
            repo_name = identifier  # fallback: use as-is
    else:
        repo_name = identifier

    filename = "README.md" if file == "readme" else "docs.md"
    docs_path: Path = settings.output_dir / repo_name / filename
    if not docs_path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"No {filename} found for '{repo_name}'. "
                "Run POST /analyze first."
            ),
        )
    return FileResponse(
        path=str(docs_path),
        filename=f"{repo_name}_{filename}",
        media_type="text/markdown",
    )

