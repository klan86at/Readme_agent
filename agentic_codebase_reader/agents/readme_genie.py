"""
agents/readme_genie.py
~~~~~~~~~~~~~~~~~~~~~~
ReadmeGenie agent — generates a concise, GitHub-ready README.md.
"""
from __future__ import annotations

import logging
from pathlib import Path

from agentic_codebase_reader.models.file_tree import FileTree, NodeType
from agentic_codebase_reader.services.llm_service import get_llm_client

logger = logging.getLogger(__name__)

# Languages that have a standard shields.io badge
BADGE_MAP: dict[str, str] = {
    "Python":     "https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white",
    "JavaScript": "https://img.shields.io/badge/JavaScript-F7DF1E?style=flat&logo=javascript&logoColor=black",
    "TypeScript": "https://img.shields.io/badge/TypeScript-3178C6?style=flat&logo=typescript&logoColor=white",
    "Rust":       "https://img.shields.io/badge/Rust-000000?style=flat&logo=rust&logoColor=white",
    "Go":         "https://img.shields.io/badge/Go-00ADD8?style=flat&logo=go&logoColor=white",
    "Java":       "https://img.shields.io/badge/Java-ED8B00?style=flat&logo=java&logoColor=white",
    "C":          "https://img.shields.io/badge/C-00599C?style=flat&logo=c&logoColor=white",
    "C++":        "https://img.shields.io/badge/C++-00599C?style=flat&logo=cplusplus&logoColor=white",
    "Ruby":       "https://img.shields.io/badge/Ruby-CC342D?style=flat&logo=ruby&logoColor=white",
    "PHP":        "https://img.shields.io/badge/PHP-777BB4?style=flat&logo=php&logoColor=white",
}


class ReadmeGenie:
    """Generates a concise, GitHub-ready README.md from pipeline context."""

    # ── Public API ────────────────────────────────────────────────────────────

    async def generate_readme(
        self,
        repo_name: str,
        repo_url: str,
        file_tree: FileTree,
        readme_summary: str,
    ) -> str:
        """Assemble a GitHub README from the repo context.

        Args:
            repo_name:      Repository name.
            repo_url:       Original GitHub URL.
            file_tree:      FileTree from Repo Mapper.
            readme_summary: README summary from Repo Mapper.

        Returns:
            A complete Markdown string ready to be saved as README.md.
        """
        llm = get_llm_client()

        # Render the file tree so LLM prompts always have structural context,
        # even when the original repo has no README at all.
        tree_text = self._build_structure(file_tree, max_depth=2)
        logger.info(
            "ReadmeGenie context — summary length: %d chars, tree length: %d chars",
            len(readme_summary), len(tree_text),
        )

        # Run LLM-heavy sections sequentially.
        overview   = await self._gen_overview(llm, repo_name, readme_summary, tree_text)
        features   = await self._gen_features(llm, repo_name, readme_summary, tree_text)
        quickstart = await self._gen_quickstart(llm, repo_name, readme_summary, tree_text)
        logger.info(
            "ReadmeGenie LLM results — overview: %d, features: %d, quickstart: %d chars",
            len(overview), len(features), len(quickstart),
        )

        badges    = self._build_badges(file_tree)
        structure = self._build_structure(file_tree)
        install   = self._build_installation(repo_name, file_tree)

        parts: list[str] = []

        # ── Header ────────────────────────────────────────────────────────────
        parts.append(f"# {repo_name}\n")
        parts.append(badges + "\n")

        # ── Overview ─────────────────────────────────────────────────────────
        parts.append("## Overview\n")
        parts.append(overview + "\n")

        # ── Features ─────────────────────────────────────────────────────────
        parts.append("## ✨ Features\n")
        parts.append(features + "\n")

        # ── Installation ─────────────────────────────────────────────────────
        parts.append("## 📦 Installation\n")
        parts.append(install + "\n")

        # ── Quick Start ───────────────────────────────────────────────────────
        parts.append("## 🚀 Quick Start\n")
        parts.append(quickstart + "\n")

        # ── Project Structure ─────────────────────────────────────────────────
        parts.append("## 📁 Project Structure\n")
        parts.append("```\n" + structure + "\n```\n")

        # ── Contributing ──────────────────────────────────────────────────────
        parts.append("## 🤝 Contributing\n")
        parts.append(
            "Contributions are welcome! Please open an issue or submit a pull request.\n\n"
            f"1. Fork the repository at [{repo_url}]({repo_url})\n"
            "2. Create your feature branch (`git checkout -b feature/my-feature`)\n"
            "3. Commit your changes (`git commit -m 'Add my feature'`)\n"
            "4. Push to the branch (`git push origin feature/my-feature`)\n"
            "5. Open a Pull Request\n"
        )

        # ── License ───────────────────────────────────────────────────────────
        parts.append("## 📄 License\n")
        parts.append("This project is open source. See the [LICENSE](LICENSE) file for details.\n")

        return "\n".join(parts)

    def save_readme(self, content: str, repo_name: str, output_dir: Path) -> Path:
        """Save the generated README.md to disk.

        Args:
            content:    The full README markdown string.
            repo_name:  Repository name (used as output subdirectory).
            output_dir: Base output directory.

        Returns:
            Path to the saved file.
        """
        out_dir = output_dir / repo_name
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / "README.md"
        out_path.write_text(content, encoding="utf-8")
        logger.info("README saved to %s", out_path)
        return out_path

    # ── Private helpers ───────────────────────────────────────────────────────

    async def _gen_overview(self, llm, repo_name: str, summary: str, tree_text: str) -> str:
        """Generate a 2-3 paragraph project overview."""
        context = summary if summary else "No README was provided."
        prompt = (
            f"You are writing a GitHub README for a project called '{repo_name}'.\n"
            f"Here is a summary of what the project does:\n{context}\n\n"
            f"Here is the project's directory structure:\n```\n{tree_text}\n```\n\n"
            "Using the above information, write a clear, engaging 2–3 paragraph overview section for the README.\n"
            "Do NOT include a heading. Write in plain markdown prose.\n"
            "Focus on: what it is, why it exists, and who it's for.\n"
            "Even if the summary is sparse, use the directory structure and file names to infer the project's purpose."
        )
        try:
            result = (await llm.complete(prompt, max_tokens=512)).strip()
            logger.info("Overview LLM returned %d chars", len(result))
            return result if result else (summary or "_No overview available._")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Overview generation failed: %s", exc)
            return summary or "_No overview available._"

    async def _gen_features(self, llm, repo_name: str, summary: str, tree_text: str) -> str:
        """Generate a bullet-pointed feature list."""
        context = summary if summary else "No README was provided."
        prompt = (
            f"You are writing a GitHub README for a project called '{repo_name}'.\n"
            f"Summary: {context}\n\n"
            f"Directory structure:\n```\n{tree_text}\n```\n\n"
            "Based on the summary and directory structure, list 5–8 key features of this project as GitHub markdown bullet points.\n"
            "Each bullet should start with an emoji, be concise (one line), and be impactful.\n"
            "Infer features from the code structure and file names if the summary lacks detail.\n"
            "Do NOT include a heading. Only output the bullet list."
        )
        try:
            result = (await llm.complete(prompt, max_tokens=384)).strip()
            logger.info("Features LLM returned %d chars", len(result))
            return result if result else "- _Features not available._"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Features generation failed: %s", exc)
            return "- _Features not available._"

    async def _gen_quickstart(self, llm, repo_name: str, summary: str, tree_text: str) -> str:
        """Generate a quick-start usage example."""
        context = summary if summary else "No README was provided."
        prompt = (
            f"You are writing a GitHub README for a project called '{repo_name}'.\n"
            f"Summary: {context}\n\n"
            f"Directory structure:\n```\n{tree_text}\n```\n\n"
            "Write a concise Quick Start section showing how to use this project.\n"
            "Include realistic code/command examples in fenced code blocks.\n"
            "Infer the technology stack and entry points from the directory structure.\n"
            "Do NOT include a heading. Keep it to 15–25 lines.\n"
            "If it's a Python package, show pip install and example usage."
        )
        try:
            result = (await llm.complete(prompt, max_tokens=512)).strip()
            logger.info("Quickstart LLM returned %d chars", len(result))
            return result if result else "```bash\n# See documentation for usage\n```"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Quickstart generation failed: %s", exc)
            return "```bash\n# See documentation for usage\n```"

    def _build_badges(self, file_tree: FileTree) -> str:
        """Build shields.io badge markdown for detected languages."""
        badges: list[str] = []
        for lang, url in BADGE_MAP.items():
            if lang in file_tree.languages:
                badges.append(f"![{lang}]({url})")
        if not badges:
            return ""
        return " ".join(badges)

    def _build_installation(self, repo_name: str, file_tree: FileTree) -> str:
        """Generate an installation snippet based on repo contents."""
        files = {n.name for n in self._iter_files(file_tree.root)}
        lines: list[str] = []

        if "pyproject.toml" in files or "setup.py" in files:
            lines.append("```bash")
            lines.append(f"pip install {repo_name}")
            lines.append("```")
            lines.append("\nOr install from source:")
            lines.append("```bash")
            lines.append(f"git clone {file_tree.repo_url}")
            lines.append(f"cd {repo_name}")
            lines.append("pip install -e .")
            lines.append("```")
        elif "package.json" in files:
            lines.append("```bash")
            lines.append(f"npm install {repo_name}")
            lines.append("```")
        elif "Cargo.toml" in files:
            lines.append("```bash")
            lines.append(f"cargo add {repo_name}")
            lines.append("```")
        else:
            lines.append("```bash")
            lines.append(f"git clone {file_tree.repo_url}")
            lines.append(f"cd {repo_name}")
            lines.append("```")

        return "\n".join(lines)

    def _build_structure(self, file_tree: FileTree, max_depth: int = 3) -> str:
        """Render a compact file tree (max 3 levels)."""
        lines: list[str] = [f"{file_tree.repo_name}/"]
        self._render_node(file_tree.root, lines, "", 0, max_depth)
        return "\n".join(lines)

    def _render_node(
        self, node, lines: list[str], prefix: str, depth: int, max_depth: int
    ) -> None:
        from agentic_codebase_reader.models.file_tree import FileNode
        if not isinstance(node, FileNode):
            return
        children = node.children
        for i, child in enumerate(children):
            is_last = i == len(children) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{child.name}")
            if child.node_type == NodeType.DIRECTORY:
                if depth < max_depth:
                    ext = "    " if is_last else "│   "
                    self._render_node(child, lines, prefix + ext, depth + 1, max_depth)
                else:
                    ext = "    " if is_last else "│   "
                    lines.append(f"{prefix + ext}└── ...")

    def _iter_files(self, node):
        """Flatten all file nodes from a tree."""
        from agentic_codebase_reader.models.file_tree import FileNode
        if not isinstance(node, FileNode):
            return
        if node.node_type == NodeType.DIRECTORY:
            for child in node.children:
                yield from self._iter_files(child)
        else:
            yield node
