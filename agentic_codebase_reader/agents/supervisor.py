"""
agents/supervisor.py
~~~~~~~~~~~~~~~~~~~~
Code Genius — the Supervisor agent that orchestrates the full pipeline.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

from agentic_codebase_reader.config import settings
from agentic_codebase_reader.models.code_graph import CodeContextGraph
from agentic_codebase_reader.models.doc_sections import DocReport
from agentic_codebase_reader.models.file_tree import FileTree, NodeType

logger = logging.getLogger(__name__)

ENTRY_POINT_PATTERNS: list[str] = [
    "main.py", "app.py", "run.py", "server.py", "manage.py", "__main__.py",
    "cli.py", "wsgi.py", "asgi.py",
]


@dataclass
class PipelineContext:
    """Shared mutable state threaded through the pipeline."""

    repo_url: str
    repo_name: str = ""
    clone_path: Path | None = None
    file_tree: FileTree | None = None
    readme_summary: str = ""
    code_graph: CodeContextGraph | None = None
    priority_files: list[Path] = field(default_factory=list)
    cache_name: str | None = None
    errors: list[str] = field(default_factory=list)


class Supervisor:
    """Code Genius — orchestrates the multi-agent documentation pipeline.

    Usage::

        supervisor = Supervisor()
        report = await supervisor.run("https://github.com/owner/repo")
    """

    def __init__(self) -> None:
        from agentic_codebase_reader.agents.code_analyzer import CodeAnalyzer
        from agentic_codebase_reader.agents.doc_genie import DocGenie
        from agentic_codebase_reader.agents.repo_mapper import RepoMapper
        from agentic_codebase_reader.services.git_service import GitService

        self._git = GitService()
        self._mapper = RepoMapper()
        self._analyzer = CodeAnalyzer()
        self._genie = DocGenie()

    async def run(self, repo_url: str, mode: str = "docs") -> DocReport:
        """Execute the full pipeline for the given GitHub URL.

        Steps:
            1. Validate URL.
            2. Check repo size.
            3. Clone repo.
            4. Repo Mapper → file tree + README summary.
            5. Plan priority files.
            6. Code Analyzer → CCG (high-priority first, then rest).
            7. DocGenie → Markdown report.
            8. Save output.
            9. Cleanup clone.

        Args:
            repo_url: A public GitHub repository URL.

        Returns:
            A :class:`DocReport` containing the assembled documentation.

        Raises:
            ValueError:   If the URL is invalid or unreachable.
            RuntimeError: If a critical pipeline step fails.
        """
        ctx = PipelineContext(
            repo_url=repo_url,
            repo_name=self._extract_repo_name(repo_url),
        )
        logger.info("Pipeline started for %s (mode=%s)", repo_url, mode)

        # ── Step 1: Validate URL ──────────────────────────────────────────────
        try:
            self._git.validate_url(repo_url)
        except Exception as exc:
            raise ValueError(f"Repository not accessible: {exc}") from exc

        # ── Step 2: Size guard ────────────────────────────────────────────────
        try:
            size_mb = self._git.get_repo_size_mb(repo_url)
            if size_mb > settings.max_repo_size_mb:
                raise ValueError(
                    f"Repository is {size_mb:.0f} MB — exceeds limit of "
                    f"{settings.max_repo_size_mb} MB."
                )
            logger.info("Repository size: %.1f MB", size_mb)
        except ValueError:
            raise
        except Exception as exc:
            logger.warning("Could not check repo size: %s", exc)
            ctx.errors.append(f"Size check skipped: {exc}")

        # ── Step 3: Clone ─────────────────────────────────────────────────────
        try:
            ctx.clone_path = self._git.clone(repo_url)
        except Exception as exc:
            raise RuntimeError(f"Clone failed: {exc}") from exc

        try:
            # ── Step 4: Repo Mapper ───────────────────────────────────────────
            ctx.file_tree = self._mapper.build_file_tree(
                ctx.clone_path, repo_url, ctx.repo_name
            )
            # Step 4: Summarise README
            logger.info("Step 4: Summarising README (or generating fallback)...")
            ctx.readme_summary = await self._mapper.summarize_readme(
                ctx.clone_path, file_tree=ctx.file_tree
            )
            logger.info("File tree: %d files", ctx.file_tree.total_files)

            # ── Step 5: Plan priority files ───────────────────────────────────
            ctx.priority_files = self._plan_priority_files(ctx)

            # ── Step 5b: Create context cache (docs mode only) ────────────────
            if mode == "docs" and settings.llm_provider == "google":
                from agentic_codebase_reader.services.llm_service import GeminiClient
                from agentic_codebase_reader.agents.repo_mapper import RepoMapper
                gemini = GeminiClient()
                tree_text = RepoMapper().render_tree_text(ctx.file_tree, max_depth=5)
                context_str = (
                    f"Repository: {ctx.repo_name} ({ctx.repo_url})\n\n"
                    f"README Summary:\n{ctx.readme_summary}\n\n"
                    f"File Tree:\n{tree_text}"
                )
                ctx.cache_name = gemini.create_context_cache(context_str)

            # ── Step 6: Build CCG (docs mode only) ───────────────────────────
            if mode == "docs":
                ctx.code_graph = self._analyzer.build_code_graph(
                    ctx.priority_files, repo_name=ctx.repo_name
                )
            else:
                from agentic_codebase_reader.models.code_graph import CodeContextGraph
                ctx.code_graph = CodeContextGraph(repo_name=ctx.repo_name)

            # ── Step 7: Generate docs / README ────────────────────────────────
            if mode == "readme":
                from agentic_codebase_reader.agents.readme_genie import ReadmeGenie
                readme_content = await ReadmeGenie().generate_readme(
                    repo_name=ctx.repo_name,
                    repo_url=ctx.repo_url,
                    file_tree=ctx.file_tree,
                    readme_summary=ctx.readme_summary,
                )
                settings.output_dir.mkdir(parents=True, exist_ok=True)
                out_path = ReadmeGenie().save_readme(
                    readme_content, ctx.repo_name, settings.output_dir
                )
                from agentic_codebase_reader.models.doc_sections import DocReport
                report = DocReport(
                    repo_name=ctx.repo_name,
                    repo_url=ctx.repo_url,
                    sections=[],
                    output_path=out_path,
                )
            else:
                report = await self._genie.generate_docs(
                    repo_name=ctx.repo_name,
                    repo_url=ctx.repo_url,
                    file_tree=ctx.file_tree,
                    readme_summary=ctx.readme_summary,
                    code_graph=ctx.code_graph,
                    cache_name=ctx.cache_name,
                )

                # ── Step 8: Save output ───────────────────────────────────────
                settings.output_dir.mkdir(parents=True, exist_ok=True)
                self._genie.save_docs(report, output_dir=settings.output_dir)

        finally:
            # ── Step 9: Cleanup ───────────────────────────────────────────────
            if ctx.cache_name and settings.llm_provider == "google":
                from agentic_codebase_reader.services.llm_service import GeminiClient
                GeminiClient().delete_context_cache(ctx.cache_name)
            if ctx.clone_path:
                self._git.cleanup(ctx.clone_path)
                logger.debug("Temporary clone cleaned up.")


        logger.info("Pipeline complete — output: %s", report.output_path)
        return report

    # ── Private helpers ───────────────────────────────────────────────────────

    def _plan_priority_files(self, ctx: PipelineContext) -> list[Path]:
        """Collect all source files, entry points first."""
        if ctx.file_tree is None or ctx.clone_path is None:
            return []

        all_files = self._collect_source_files(ctx.file_tree.root, ctx.clone_path)

        entry_points: list[Path] = []
        rest: list[Path] = []
        for fp in all_files:
            if fp.name in ENTRY_POINT_PATTERNS:
                entry_points.append(fp)
            else:
                rest.append(fp)

        logger.info(
            "Priority plan: %d entry points + %d other files",
            len(entry_points), len(rest),
        )
        return entry_points + rest

    def _collect_source_files(
        self, node: object, clone_root: Path
    ) -> list[Path]:
        """Recursively collect all source file paths from the file tree."""
        from agentic_codebase_reader.models.file_tree import FileNode

        if not isinstance(node, FileNode):
            return []

        result: list[Path] = []
        if node.node_type == NodeType.FILE and node.language is not None:
            result.append(clone_root / node.path)
        for child in node.children:
            result.extend(self._collect_source_files(child, clone_root))
        return result

    @staticmethod
    def _extract_repo_name(repo_url: str) -> str:
        """Parse a GitHub URL and return the repository name."""
        path = urlparse(repo_url).path.strip("/")
        parts = path.split("/")
        if len(parts) < 2 or not parts[1]:
            raise ValueError(f"Cannot extract repo name from: {repo_url!r}")
        return parts[1].removesuffix(".git")
