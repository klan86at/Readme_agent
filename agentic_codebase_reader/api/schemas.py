"""
api/schemas.py
~~~~~~~~~~~~~~
Pydantic request / response schemas for the HTTP API.
"""
from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl


class AnalyzeRequest(BaseModel):
    """Request body for POST /analyze.

    Attributes:
        repo_url: A public GitHub repository URL.
        mode:     Generation mode — ``"docs"`` (full technical reference, default)
                  or ``"readme"`` (concise GitHub README).
    """

    repo_url: HttpUrl = Field(
        ...,
        examples=["https://github.com/owner/repo"],
        description="Public GitHub repository URL to document.",
    )
    mode: str = Field(
        default="docs",
        pattern="^(docs|readme)$",
        description="Output mode: 'docs' for full reference, 'readme' for GitHub README.",
    )


class AnalyzeResponse(BaseModel):
    """Response body for POST /analyze.

    Attributes:
        repo_name:   Parsed repository name.
        status:      Pipeline status: "completed" or "error".
        output_path: Relative path to the generated docs (on success).
        error:       Error message (on failure).
    """

    repo_name: str
    status: str
    output_path: str | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: str = "ok"
    version: str
