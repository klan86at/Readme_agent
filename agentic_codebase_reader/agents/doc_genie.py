"""
agents/doc_genie.py
~~~~~~~~~~~~~~~~~~~
DocGenie agent — synthesises Markdown documentation from pipeline context.
"""
from __future__ import annotations

import logging
from pathlib import Path

from agentic_codebase_reader.config import settings
from agentic_codebase_reader.models.code_graph import CodeContextGraph, SymbolKind
from agentic_codebase_reader.models.doc_sections import Diagram, DocReport, DocSection
from agentic_codebase_reader.models.file_tree import FileTree
from agentic_codebase_reader.services.diagram_service import DiagramService

logger = logging.getLogger(__name__)

SECTION_ORDER: list[str] = [
    "Project Overview",
    "Repository Structure",
    "Installation",
    "Usage",
    "Architecture & Diagrams",
    "API Reference",
    "Module Index",
]

_diagram_svc = DiagramService()


class DocGenie:
    """Synthesises the final Markdown documentation."""

    # ── Public API ────────────────────────────────────────────────────────────

    async def generate_docs(
        self,
        repo_name: str,
        repo_url: str,
        file_tree: FileTree,
        readme_summary: str,
        code_graph: CodeContextGraph,
        cache_name: str | None = None,
    ) -> DocReport:
        """Assemble the complete documentation report.

        Args:
            repo_name:      Repository name.
            repo_url:       Original GitHub URL.
            file_tree:      FileTree from Repo Mapper.
            readme_summary: README summary from Repo Mapper.
            code_graph:     CCG from Code Analyzer.
            cache_name:     Optional Gemini context cache name for faster LLM calls.

        Returns:
            A fully populated :class:`DocReport`.
        """
        sections: list[DocSection] = []

        sections.append(
            await self._build_overview_section(repo_name, repo_url, readme_summary, cache_name)
        )
        sections.append(self._build_structure_section(file_tree))
        sections.append(self._build_installation_section(repo_name))
        sections.append(self._build_usage_section(repo_name))
        sections.append(self._build_diagram_section(code_graph))
        sections.append(await self._build_api_reference_section(code_graph, cache_name))
        sections.append(self._build_module_index_section(file_tree))

        # Re-order by canonical section ordering.
        order_map = {title: i for i, title in enumerate(SECTION_ORDER)}
        sections.sort(key=lambda s: order_map.get(s.heading, 99))
        for i, sec in enumerate(sections):
            sec.order = i

        report = DocReport(
            repo_name=repo_name,
            repo_url=repo_url,
            sections=sections,
        )
        return report

    def save_docs(self, report: DocReport, output_dir: Path) -> Path:
        """Render and save the documentation to disk.

        Args:
            report:     The fully assembled :class:`DocReport`.
            output_dir: Root output directory.

        Returns:
            Absolute path to the saved ``docs.md``.
        """
        out_path = output_dir / report.repo_name / "docs.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        markdown = report.to_markdown()
        out_path.write_text(markdown, encoding="utf-8")
        report.output_path = out_path
        logger.info("Documentation saved to %s", out_path)
        return out_path

    # ── Section builders ──────────────────────────────────────────────────────

    async def _build_overview_section(
        self,
        repo_name: str,
        repo_url: str,
        readme_summary: str,
        cache_name: str | None = None,
    ) -> DocSection:
        """Generate the Project Overview section."""
        from agentic_codebase_reader.services.llm_service import GeminiClient, get_llm_client

        if readme_summary:
            prompt = (
                "You are a technical writer. Expand the following one-paragraph summary "
                "into a clear, engaging project overview section (3–5 sentences). "
                "Include what the project does, why it exists, and who it is for.\n\n"
                f"Summary: {readme_summary}\n\nRepository: {repo_url}"
            )
            try:
                if cache_name and settings.llm_provider == "google":
                    gemini = GeminiClient()
                    content = await gemini.complete_with_cache(cache_name, prompt, max_tokens=400)
                else:
                    llm = get_llm_client()
                    content = await llm.complete(prompt, max_tokens=400)
            except Exception as exc:  # noqa: BLE001
                logger.warning("LLM overview generation failed: %s", exc)
                content = readme_summary
        else:
            content = (
                f"**{repo_name}** is hosted at [{repo_url}]({repo_url}).\n\n"
                "_No README was found in this repository._"
            )

        return DocSection(
            heading="Project Overview",
            content=content.strip(),
            order=0,
        )

    def _build_structure_section(self, file_tree: FileTree) -> DocSection:
        """Generate the Repository Structure section."""
        from agentic_codebase_reader.agents.repo_mapper import RepoMapper

        mapper = RepoMapper()
        tree_text = mapper.render_tree_text(file_tree, max_depth=4)

        lang_table_rows = "\n".join(
            f"| {lang} | {count} |"
            for lang, count in sorted(
                file_tree.languages.items(), key=lambda x: -x[1]
            )
        )
        lang_table = (
            "| Language | Files |\n|---|---|\n" + lang_table_rows
            if lang_table_rows
            else "_No recognised source files._"
        )

        content = (
            f"Total files: **{file_tree.total_files}**\n\n"
            f"### Language Distribution\n\n{lang_table}\n\n"
            f"### Directory Layout\n\n```\n{tree_text}\n```"
        )
        return DocSection(heading="Repository Structure", content=content, order=1)

    def _build_installation_section(self, repo_name: str) -> DocSection:
        content = (
            "```bash\n"
            f"git clone https://github.com/<owner>/{repo_name}\n"
            f"cd {repo_name}\n"
            "pip install -r requirements.txt\n"
            "# or with uv:\n"
            "uv venv && uv pip install -r requirements.txt\n"
            "```"
        )
        return DocSection(heading="Installation", content=content, order=2)

    def _build_usage_section(self, repo_name: str) -> DocSection:
        content = (
            "Refer to the project README and entry-point files "
            "(e.g. `main.py`, `app.py`) for usage instructions.\n\n"
            "**Quick start:**\n\n"
            "```bash\n"
            f"python main.py  # or the project's primary entry point\n"
            "```"
        )
        return DocSection(heading="Usage", content=content, order=3)

    def _build_diagram_section(self, code_graph: CodeContextGraph) -> DocSection:
        """Generate the Architecture & Diagrams section."""
        diagrams: list[Diagram] = []

        class_diag = _diagram_svc.class_diagram(code_graph)
        call_diag = _diagram_svc.call_graph(code_graph)
        mod_diag = _diagram_svc.module_dependency_graph(code_graph)
        diagrams.extend([class_diag, call_diag, mod_diag])

        def _render_diagram(d: Diagram) -> str:
            caption = f"\n> {d.caption}" if d.caption else ""
            return f"### {d.title}\n\n```mermaid\n{d.content}\n```{caption}"

        content = "\n\n".join(_render_diagram(d) for d in diagrams)
        return DocSection(
            heading="Architecture & Diagrams",
            content=content,
            diagrams=diagrams,
            order=4,
        )

    # Maximum symbols shown per module in the API reference table.
    _MAX_SYMBOLS_PER_MODULE = 30
    # Maximum modules for which we generate LLM descriptions (to cap cost).
    _MAX_LLM_MODULES = 5

    async def _build_api_reference_section(
        self,
        code_graph: CodeContextGraph,
        cache_name: str | None = None,
    ) -> DocSection:
        """Generate the API Reference section.

        Uses a single batched LLM call per module (not per function) to
        generate descriptions for undocumented symbols — keeping total
        API calls to at most _MAX_LLM_MODULES.
        When a Gemini context cache is active, uses complete_with_cache()
        to avoid re-sending the repository context on each call.
        """
        from agentic_codebase_reader.services.llm_service import GeminiClient, get_llm_client

        # Group symbols by module (parent of their id).
        modules: dict[str, list] = {}
        for node in code_graph.nodes:
            parts = node.id.rsplit(".", 1)
            mod = parts[0] if len(parts) > 1 else "root"
            modules.setdefault(mod, []).append(node)

        sections_md: list[str] = []
        llm = get_llm_client()
        llm_calls_made = 0

        for mod, nodes in sorted(modules.items()):
            # Cap symbols per module for readability.
            visible_nodes = sorted(nodes, key=lambda n: n.name)[: self._MAX_SYMBOLS_PER_MODULE]

            # ── Single batched LLM call per module ────────────────────────────
            undocumented: list[tuple[int, str]] = []   # (index_in_visible, sig)
            for idx, node in enumerate(visible_nodes):
                if not node.docstring and node.kind == SymbolKind.FUNCTION:
                    undocumented.append((idx, (node.signature or node.name)[:120]))

            generated_docs: dict[int, str] = {}
            if undocumented and llm_calls_made < self._MAX_LLM_MODULES:
                sigs_block = "\n".join(
                    f"{i+1}. {sig}" for i, (_, sig) in enumerate(undocumented)
                )
                prompt = (
                    "You are a technical documentation assistant.\n"
                    "For each numbered Python function signature below, write ONE concise "
                    "sentence (max 15 words) describing what it likely does.\n"
                    "Reply ONLY with numbered lines matching the input, e.g.:\n"
                    "1. Initialises the application with the given config.\n"
                    "2. Returns the current user session.\n\n"
                    f"Signatures:\n{sigs_block}"
                )
                try:
                    if cache_name and settings.llm_provider == "google":
                        gemini = GeminiClient()
                        raw = await gemini.complete_with_cache(cache_name, prompt, max_tokens=400)
                    else:
                        llm = get_llm_client()
                        raw = await llm.complete(prompt, max_tokens=400)
                    llm_calls_made += 1
                    for line in raw.strip().splitlines():
                        line = line.strip()
                        if line and line[0].isdigit() and ". " in line:
                            num_str, desc = line.split(". ", 1)
                            try:
                                num = int(num_str) - 1
                                original_idx = undocumented[num][0]
                                generated_docs[original_idx] = desc.strip().rstrip(".")
                            except (ValueError, IndexError):
                                pass
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Batch LLM call failed for module %s: %s", mod, exc)

            # ── Build table rows ───────────────────────────────────────────────
            rows = []
            for idx, node in enumerate(visible_nodes):
                kind_icon = "🔷" if node.kind == SymbolKind.CLASS else "🔹"
                sig = (node.signature or node.name)[:80]
                doc = node.docstring or generated_docs.get(idx, "_No description._")
                rows.append(f"| {kind_icon} `{node.name}` | `{sig}` | {doc} |")

            table = (
                "| Symbol | Signature | Description |\n"
                "|---|---|---|\n"
                + "\n".join(rows)
            )
            sections_md.append(f"#### `{mod}`\n\n{table}")

        content = "\n\n".join(sections_md) if sections_md else "_No symbols found._"
        return DocSection(heading="API Reference", content=content, order=5)

    def _build_module_index_section(self, file_tree: FileTree) -> DocSection:
        """Generate a flat module index listing all source files."""
        from agentic_codebase_reader.models.file_tree import NodeType

        py_files: list[str] = []

        def _collect(node: object) -> None:
            from agentic_codebase_reader.models.file_tree import FileNode
            if not isinstance(node, FileNode):
                return
            if node.node_type == NodeType.FILE and node.language:
                py_files.append(f"- `{node.path}` ({node.language})")
            for child in node.children:
                _collect(child)

        _collect(file_tree.root)

        content = (
            "\n".join(py_files)
            if py_files
            else "_No recognised source files found._"
        )
        return DocSection(heading="Module Index", content=content, order=6)
