"""
config.py
~~~~~~~~~
Application settings loaded from environment variables (via .env file).
"""
from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing_extensions import Self

# Always resolve .env relative to the project root (parent of this file's dir),
# regardless of the current working directory.
_PROJECT_ROOT = Path(__file__).parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Central configuration for Codebase Reader.

    All values can be overridden via environment variables or a .env file.
    """

    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),   # absolute path — always found
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM ──────────────────────────────────────────────────────────────────
    llm_provider: Literal["google", "openai"] = Field(
        default="google",
        description="Which LLM backend to use.",
    )

    # Google Gemini
    google_api_key: str = Field(default="", description="Google Gemini API key.")
    google_model: str = Field(default="gemini-2.5-flash", description="Gemini model name.")

    # OpenAI
    openai_api_key: str = Field(default="", description="OpenAI API key.")
    openai_model: str = Field(default="gpt-4o-mini", description="OpenAI model name.")

    # ── API Server ────────────────────────────────────────────────────────────
    api_host: str = Field(default="0.0.0.0", description="Bind host for the API server.")
    api_port: int = Field(default=8000, description="Bind port for the API server.")

    # ── Storage ───────────────────────────────────────────────────────────────
    output_dir: Path = Field(
        default=Path("./outputs"),
        description="Root directory where generated docs are saved.",
    )
    clone_tmp_dir: Path | None = Field(
        default=None,
        description="Temp dir for cloned repos. None = system default.",
    )

    # ── Safety ────────────────────────────────────────────────────────────────
    max_repo_size_mb: int = Field(
        default=500,
        description="Maximum repository size (MB) this system will accept.",
    )

    # ── Logging ───────────────────────────────────────────────────────────────
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Python logging level.",
    )


    @model_validator(mode="after")
    def _validate_api_key(self) -> Self:
        """Raise a clear error if the selected LLM provider has no API key."""
        if self.llm_provider == "google" and not self.google_api_key:
            raise ValueError(
                "GOOGLE_API_KEY is not set. "
                f"Add it to your .env file at: {_ENV_FILE}"
            )
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. "
                f"Add it to your .env file at: {_ENV_FILE}"
            )
        return self


# Singleton instance — import this throughout the project.
settings = Settings()
