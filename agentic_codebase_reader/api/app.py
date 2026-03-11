"""
api/app.py
~~~~~~~~~~
FastAPI application factory.

Usage (development)::

    uvicorn agentic_codebase_reader.api.app:create_app --factory --reload

Usage (production)::

    uvicorn agentic_codebase_reader.api.app:create_app --factory \
        --host 0.0.0.0 --port 8000 --workers 4
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agentic_codebase_reader import __version__
from agentic_codebase_reader.api.routes import router
from agentic_codebase_reader.config import settings

logger = logging.getLogger(__name__)

# Resolve the frontend directory relative to the project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_FRONTEND_DIR = _PROJECT_ROOT / "frontend"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        A configured :class:`fastapi.FastAPI` instance ready to serve.
    """
    logging.basicConfig(level=settings.log_level)

    app = FastAPI(
        title="Codebase Reader API",
        description=(
            "Multi-agent system that generates Markdown documentation "
            "for public GitHub repositories."
        ),
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Allow all origins in development. Tighten in production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Mount API routes first (takes priority over static files).
    app.include_router(router)

    # Serve frontend static files at root — index.html → http://localhost:8000/
    if _FRONTEND_DIR.is_dir():
        app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")

    @app.on_event("startup")
    async def _startup() -> None:
        logger.info("Codebase Reader API v%s starting up.", __version__)
        settings.output_dir.mkdir(parents=True, exist_ok=True)

    return app

