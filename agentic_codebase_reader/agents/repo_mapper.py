"""
agents/repo_mapper.py
~~~~~~~~~~~~~~~~~~~~~
Repo Mapper agent — clones, maps, and summarises a repository.
"""
from __future__ import annotations

import logging
from pathlib import Path

from agentic_codebase_reader.models.file_tree import FileNode, FileTree, NodeType
from agentic_codebase_reader.services.parser_service import ParserService

logger = logging.getLogger(__name__)

IGNORED_DIRS: set[str] = {
    ".git", ".github", ".env", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".ruff_cache", "node_modules", ".venv",
    "venv", "env", "dist", "build", ".eggs", ".tox", "htmlcov",
    # Test directories
    "tests", "test", "testing", "__tests__", "spec", "specs",
}

IGNORED_FILES: set[str] = {
    "conftest.py", "pytest.ini", "tox.ini", "setup.py", "setup.cfg",
    "noxfile.py", "manage.py",
}

README_CANDIDATES: list[str] = [
    "README.md", "readme.md", "README.rst", "README.txt", "README",
]

_parser_service = ParserService()


class RepoMapper:
    """Clones a repository and produces a structured map of its contents."""

    # ── Public API ────────────────────────────────────────────────────────────

    def build_file_tree(
        self,
        repo_path: Path,
        repo_url: str,
        repo_name: str,
    ) -> FileTree:
        """Traverse the cloned repository and build a :class:`FileTree`.

        Ignores directories in :data:`IGNORED_DIRS` and any hidden dir
        (name starts with ``.``).

        Args:
            repo_path:  Absolute path to the cloned repository root.
            repo_url:   Original GitHub URL.
            repo_name:  Repository name.

        Returns:
            A populated :class:`FileTree`.
        """
        root_node = self._build_node(repo_path, repo_path)
        total_files, lang_counts = self._count_stats(root_node)

        logger.info(
            "File tree built: %d files, languages: %s",
            total_files, lang_counts,
        )
        return FileTree(
            repo_name=repo_name,
            repo_url=repo_url,
            root=root_node,
            total_files=total_files,
            languages=lang_counts,
        )

    async def summarize_readme(
        self,
        repo_path: Path,
        file_tree: FileTree | None = None,
    ) -> str:
        """Locate and summarise the repository README via LLM.
        
        If no README is found and a ``file_tree`` is provided, the LLM will
        attempt to infer a summary based on the project's directory structure.

        Args:
            repo_path: Absolute path to the cloned repository root.
            file_tree: Optional file tree to use as a fallback if no README exists.

        Returns:
            A concise summary string, or ``""`` if no README found and no tree provided.
        """
        readme_path = self._find_readme(repo_path)
        if readme_path is None:
            if file_tree:
                logger.info("No README found. Generating fallback summary from file tree.")
                return await self._generate_fallback_summary(file_tree)
            logger.warning("No README found in %s and no file tree provided for fallback.", repo_path)
            return ""

        content = readme_path.read_text(encoding="utf-8", errors="replace")
        # Trim very large READMEs to avoid hitting token limits.
        content = content[:8000]

        from agentic_codebase_reader.services.llm_service import get_llm_client

        llm = get_llm_client()
        prompt = (
            "You are a technical documentation assistant.\n"
            "Summarise the following README in at most 5 clear, concise sentences.\n"
            "Focus on: what the project does, its key features, and its primary use-case.\n\n"
            f"README:\n{content}"
        )
        try:
            summary = await llm.complete(prompt, max_tokens=512)
            logger.debug("README summary generated (%d chars)", len(summary))
            return summary.strip()
        except Exception as exc:  # noqa: BLE001
            logger.error("LLM summarisation failed: %s", exc)
            # Fallback: return the first 500 chars of the raw README.
            return content[:500].strip()

    async def _generate_fallback_summary(self, file_tree: FileTree) -> str:
        """Infer a project summary purely from its directory and file structure."""
        tree_text = self.render_tree_text(file_tree, max_depth=2)
        
        from agentic_codebase_reader.services.llm_service import get_llm_client
        llm = get_llm_client()
        
        prompt = (
            "You are a technical documentation assistant analyzing a codebase that lacks a README.\n"
            "Based on the following directory structure and file names, infer what this project is and what it likely does.\n"
            "Provide a concise summary in at most 3 clear sentences.\n\n"
            "Directory Structure:\n"
            f"```text\n{tree_text}\n```"
        )
        try:
            summary = await llm.complete(prompt, max_tokens=512)
            logger.debug("Fallback summary generated (%d chars)", len(summary))
            return summary.strip()
        except Exception as exc:  # noqa: BLE001
            logger.error("LLM fallback summarisation failed: %s", exc)
            return ""

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_node(self, path: Path, repo_root: Path) -> FileNode:
        """Recursively build a :class:`FileNode` for a file or directory."""
        rel = path.relative_to(repo_root)

        if path.is_dir():
            children: list[FileNode] = []
            try:
                entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
            except PermissionError:
                entries = []

            for entry in entries:
                # Skip ignored directories and hidden dirs (except root).
                if entry.is_dir():
                    if entry.name in IGNORED_DIRS or (
                        entry.name.startswith(".") and entry != repo_root
                    ):
                        continue
                
                child_node = self._build_node(entry, repo_root)
                if child_node is not None:
                    children.append(child_node)

            return FileNode(
                name=path.name or repo_root.name,
                path=rel,
                node_type=NodeType.DIRECTORY,
                children=children,
            )

        # It's a file.
        # Skip explicitly ignored files and test files.
        file_name = path.name
        if file_name in IGNORED_FILES or file_name.startswith("test_") or file_name.endswith(("_test.py", "_spec.py")):
            return None  # type: ignore[return-value]

        try:
            size = path.stat().st_size
        except OSError:
            size = 0

        lang = _parser_service.detect_language(path)

        return FileNode(
            name=file_name,
            path=rel,
            node_type=NodeType.FILE,
            size=size,
            language=lang,
        )

    @staticmethod
    def _find_readme(repo_path: Path) -> Path | None:
        """Search for a README file in the repository root."""
        for candidate in README_CANDIDATES:
            p = repo_path / candidate
            if p.exists():
                return p
        return None

    @staticmethod
    def _count_stats(
        node: FileNode,
    ) -> tuple[int, dict[str, int]]:
        """Recursively count total files and language distribution."""
        if node.node_type == NodeType.FILE:
            lang_counts = {}
            if node.language:
                lang_counts[node.language] = 1
            return 1, lang_counts

        total = 0
        lang_counts: dict[str, int] = {}
        for child in node.children:
            c_total, c_langs = RepoMapper._count_stats(child)
            total += c_total
            for lang, count in c_langs.items():
                lang_counts[lang] = lang_counts.get(lang, 0) + count
        return total, lang_counts

    def render_tree_text(self, tree: FileTree, max_depth: int = 4) -> str:
        """Render a file tree as a plain-text string (for Markdown code blocks).

        Args:
            tree:      The :class:`FileTree` to render.
            max_depth: Maximum directory depth to display.

        Returns:
            A multi-line string representation of the tree.
        """
        lines: list[str] = [f"{tree.repo_name}/"]
        self._render_node(tree.root, lines, prefix="", depth=0, max_depth=max_depth)
        return "\n".join(lines)

    def _render_node(
        self,
        node: FileNode,
        lines: list[str],
        prefix: str,
        depth: int,
        max_depth: int,
    ) -> None:
        """Recursively render nodes into ``lines``."""
        children = node.children
        for i, child in enumerate(children):
            is_last = i == len(children) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{child.name}")

            if child.node_type == NodeType.DIRECTORY and depth < max_depth:
                extension = "    " if is_last else "│   "
                self._render_node(
                    child, lines, prefix + extension, depth + 1, max_depth
                )
            elif child.node_type == NodeType.DIRECTORY and depth >= max_depth:
                is_last2 = True
                ext2 = "    " if is_last else "│   "
                lines.append(f"{prefix + ext2}└── ...")
