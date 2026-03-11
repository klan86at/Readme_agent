"""
agents/code_analyzer.py
~~~~~~~~~~~~~~~~~~~~~~~
Code Analyzer agent — parses source files and builds the Code Context Graph.
"""
from __future__ import annotations

import logging
from pathlib import Path

import networkx as nx

from agentic_codebase_reader.models.code_graph import (
    CodeContextGraph,
    EdgeKind,
    GraphEdge,
    SymbolKind,
    SymbolNode,
)
from agentic_codebase_reader.services.parser_service import (
    EXTENSION_TO_LANGUAGE,
    ParserService,
    ParserServiceError,
)

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = set(EXTENSION_TO_LANGUAGE.keys())

_parser = ParserService()


class CodeAnalyzer:
    """Parses source files and constructs the Code Context Graph (CCG)."""

    # ── Public API ────────────────────────────────────────────────────────────

    def build_code_graph(
        self,
        file_paths: list[Path],
        repo_name: str,
    ) -> CodeContextGraph:
        """Parse all supplied files and build the Code Context Graph.

        Args:
            file_paths: List of absolute paths to source files.
            repo_name:  Repository name.

        Returns:
            A populated :class:`CodeContextGraph` backed by a NetworkX DiGraph.
        """
        graph = CodeContextGraph(repo_name=repo_name)
        # NetworkX graph for efficient traversal — stored as private attr.
        nx_graph: nx.DiGraph = nx.DiGraph()

        for file_path in file_paths:
            if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            try:
                nodes = self.parse_file(file_path)
                edges = self.extract_edges(file_path, nodes)
                graph.nodes.extend(nodes)
                graph.edges.extend(edges)
                for node in nodes:
                    nx_graph.add_node(node.id, data=node)
                for edge in edges:
                    nx_graph.add_edge(
                        edge.source_id, edge.target_id, kind=edge.kind
                    )
            except (ParserServiceError, ValueError, OSError) as exc:
                logger.warning("Skipping %s — parse error: %s", file_path, exc)

        # Attach the nx graph for the query helpers.
        graph.__dict__["_nx"] = nx_graph
        logger.info(
            "CCG built: %d nodes, %d edges", len(graph.nodes), len(graph.edges)
        )
        return graph

    def parse_file(self, file_path: Path) -> list[SymbolNode]:
        """Parse a single source file and extract all top-level symbols.

        Args:
            file_path: Absolute path to a source file.

        Returns:
            List of :class:`SymbolNode` objects found in the file.
        """
        try:
            tree, source = _parser.parse(file_path)
        except ValueError:
            return []  # Unsupported extension — silently skip.

        nodes: list[SymbolNode] = []
        module_id = self._file_to_module_id(file_path)

        # Extract functions.
        for fn in _parser.extract_functions(tree, source):
            node_id = f"{module_id}.{fn['name']}"
            nodes.append(
                SymbolNode(
                    id=node_id,
                    name=fn["name"],
                    kind=SymbolKind.FUNCTION,
                    file_path=file_path,
                    start_line=fn["start_line"],
                    end_line=fn["end_line"],
                    docstring=fn.get("docstring"),
                    signature=fn.get("signature"),
                )
            )

        # Extract classes (and their methods).
        for cls in _parser.extract_classes(tree, source):
            cls_id = f"{module_id}.{cls['name']}"
            nodes.append(
                SymbolNode(
                    id=cls_id,
                    name=cls["name"],
                    kind=SymbolKind.CLASS,
                    file_path=file_path,
                    start_line=cls["start_line"],
                    end_line=cls["end_line"],
                    docstring=cls.get("docstring"),
                    signature=cls.get("signature"),
                )
            )

        return nodes

    def extract_edges(
        self,
        file_path: Path,
        nodes: list[SymbolNode],
    ) -> list[GraphEdge]:
        """Extract directed relationship edges from a parsed file.

        Args:
            file_path: Absolute path to the source file.
            nodes:     Symbols already extracted from this file.

        Returns:
            List of :class:`GraphEdge` objects.
        """
        edges: list[GraphEdge] = []
        try:
            tree, source = _parser.parse(file_path)
        except ValueError:
            return edges

        module_id = self._file_to_module_id(file_path)

        # Build a lookup: symbol name → node id (for this module).
        name_to_id = {n.name: n.id for n in nodes}

        # ── CALLS edges ──────────────────────────────────────────────────────
        calls = _parser.extract_calls(tree, source)
        for call in calls:
            callee_raw: str = call["callee_name"]
            # Normalise: "self.method" → "method", "module.func" → "func"
            callee_name = callee_raw.split(".")[-1]
            if callee_name in name_to_id:
                # Intra-module call (self-referential) — source is module node.
                edges.append(GraphEdge(
                    source_id=module_id,
                    target_id=name_to_id[callee_name],
                    kind=EdgeKind.CALLS,
                ))

        # ── INHERITS edges ───────────────────────────────────────────────────
        classes = _parser.extract_classes(tree, source)
        for cls in classes:
            cls_id = f"{module_id}.{cls['name']}"
            for base in cls.get("bases", []):
                base_name = base.split(".")[-1]
                # Try to resolve to a known node in this file first.
                target_id = name_to_id.get(base_name, base_name)
                edges.append(GraphEdge(
                    source_id=cls_id,
                    target_id=target_id,
                    kind=EdgeKind.INHERITS,
                ))

        # ── IMPORTS edges ────────────────────────────────────────────────────
        imports = _parser.extract_imports(tree, source)
        for imp in imports:
            raw: str = imp.get("raw", "")
            # e.g. "from foo.bar import baz" → target "foo.bar"
            if raw.startswith("from "):
                parts = raw.split()
                if len(parts) >= 2:
                    edges.append(GraphEdge(
                        source_id=module_id,
                        target_id=parts[1],
                        kind=EdgeKind.IMPORTS,
                    ))
            elif raw.startswith("import "):
                parts = raw.split()
                if len(parts) >= 2:
                    edges.append(GraphEdge(
                        source_id=module_id,
                        target_id=parts[1],
                        kind=EdgeKind.IMPORTS,
                    ))

        return edges

    def query_graph(
        self,
        graph: CodeContextGraph,
        question: str,
    ) -> str:
        """Answer a natural-language query about the code graph.

        Simple keyword-based dispatch; extend with LLM if needed.

        Args:
            graph:    The Code Context Graph.
            question: A natural-language question (e.g. "Who calls train_model?").

        Returns:
            A formatted string answer.
        """
        q = question.lower()
        tokens = question.split()
        # Try to extract a function/class name (last capitalised or snake_case word).
        target = next(
            (t for t in reversed(tokens) if len(t) > 3 and t.isidentifier()),
            None,
        )

        if "call" in q and target:
            results = graph.callers_of(target)
            if not results:
                return f"No callers of `{target}` found in the graph."
            names = ", ".join(f"`{n.name}`" for n in results)
            return f"Functions/methods that call `{target}`: {names}."

        if "inherit" in q or "subclass" in q and target:
            results = graph.subclasses_of(target or "")
            if not results:
                return f"No subclasses of `{target}` found."
            names = ", ".join(f"`{n.name}`" for n in results)
            return f"Subclasses of `{target}`: {names}."

        return (
            f"Query not understood: {question!r}. "
            "Try: 'Which functions call X?' or 'What subclasses Y?'"
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _file_to_module_id(file_path: Path) -> str:
        """Convert a file path to a dotted module ID.

        E.g. ``/repo/foo/bar.py`` → ``foo.bar``.
        """
        parts = list(file_path.with_suffix("").parts)
        # Try to find the package root by looking for __init__.py siblings.
        for i in range(len(parts) - 1, 0, -1):
            probe = Path(*parts[:i]) / "__init__.py"
            if not probe.exists():
                return ".".join(parts[i:])
        return file_path.stem


# ── Patch CodeContextGraph with nx-powered query methods ─────────────────────

def _ccg_get_node(self: CodeContextGraph, node_id: str) -> SymbolNode | None:
    nx_g: nx.DiGraph = self.__dict__.get("_nx", nx.DiGraph())
    data = nx_g.nodes.get(node_id, {})
    return data.get("data")


def _ccg_callers_of(
    self: CodeContextGraph, function_name: str
) -> list[SymbolNode]:
    nx_g: nx.DiGraph = self.__dict__.get("_nx", nx.DiGraph())
    targets = [n for n in nx_g.nodes if n.endswith(f".{function_name}")]
    callers: list[SymbolNode] = []
    for target in targets:
        for pred in nx_g.predecessors(target):
            node_data = nx_g.nodes[pred].get("data")
            if node_data:
                callers.append(node_data)
    return callers


def _ccg_callees_of(
    self: CodeContextGraph, function_name: str
) -> list[SymbolNode]:
    nx_g: nx.DiGraph = self.__dict__.get("_nx", nx.DiGraph())
    sources = [n for n in nx_g.nodes if n.endswith(f".{function_name}")]
    callees: list[SymbolNode] = []
    for source in sources:
        for succ in nx_g.successors(source):
            node_data = nx_g.nodes[succ].get("data")
            if node_data:
                callees.append(node_data)
    return callees


def _ccg_subclasses_of(
    self: CodeContextGraph, class_name: str
) -> list[SymbolNode]:
    nx_g: nx.DiGraph = self.__dict__.get("_nx", nx.DiGraph())
    # INHERITS edges go child → parent; we want children of class_name.
    targets = [n for n in nx_g.nodes if n.endswith(f".{class_name}") or n == class_name]
    subclasses: list[SymbolNode] = []
    for target in targets:
        for pred in nx_g.predecessors(target):
            edge_data = nx_g.get_edge_data(pred, target, default={})
            if edge_data.get("kind") == EdgeKind.INHERITS:
                node_data = nx_g.nodes[pred].get("data")
                if node_data:
                    subclasses.append(node_data)
    return subclasses


# Monkey-patch the Pydantic model with live implementations.
CodeContextGraph.get_node = _ccg_get_node  # type: ignore[method-assign]
CodeContextGraph.callers_of = _ccg_callers_of  # type: ignore[method-assign]
CodeContextGraph.callees_of = _ccg_callees_of  # type: ignore[method-assign]
CodeContextGraph.subclasses_of = _ccg_subclasses_of  # type: ignore[method-assign]
