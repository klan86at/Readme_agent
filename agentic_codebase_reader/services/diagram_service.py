"""
services/diagram_service.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Mermaid diagram generation from a Code Context Graph.
"""
from __future__ import annotations

import logging
import re

from agentic_codebase_reader.models.code_graph import CodeContextGraph, EdgeKind, SymbolKind
from agentic_codebase_reader.models.doc_sections import Diagram, DiagramFormat

logger = logging.getLogger(__name__)
MAX_DIAGRAM_NODES = 30


class DiagramService:
    """Generates Mermaid diagrams from a :class:`CodeContextGraph`."""

    def class_diagram(self, graph: CodeContextGraph) -> Diagram:
        """Generate a Mermaid ``classDiagram`` for class inheritance.

        Args:
            graph: The Code Context Graph.

        Returns:
            A :class:`Diagram` with Mermaid source.
        """
        class_nodes = [n for n in graph.nodes if n.kind == SymbolKind.CLASS]
        class_nodes = class_nodes[:MAX_DIAGRAM_NODES]
        class_ids = {n.id for n in class_nodes}

        lines: list[str] = ["classDiagram"]
        for node in class_nodes:
            # Find methods (functions whose id starts with cls id + ".")
            methods = [
                m for m in graph.nodes
                if m.kind == SymbolKind.FUNCTION
                and m.id.startswith(node.id + ".")
            ]
            mid = self._to_mermaid_id(node.name)
            lines.append(f"    class {mid} {{")
            for method in methods[:8]:
                lines.append(f"        +{method.name}()")
            lines.append("    }")

        inherit_edges = [e for e in graph.edges if e.kind == EdgeKind.INHERITS]
        for edge in inherit_edges:
            src_name = edge.source_id.split(".")[-1]
            tgt_name = edge.target_id.split(".")[-1]
            src_id = self._to_mermaid_id(src_name)
            tgt_id = self._to_mermaid_id(tgt_name)
            if src_id and tgt_id:
                lines.append(f"    {tgt_id} <|-- {src_id}")

        content = "\n".join(lines)
        return Diagram(
            title="Class Hierarchy",
            format=DiagramFormat.MERMAID,
            content=content,
            caption="Inheritance relationships between classes.",
        )

    def call_graph(
        self,
        graph: CodeContextGraph,
        root: str | None = None,
        max_depth: int = 3,
    ) -> Diagram:
        """Generate a Mermaid ``graph TD`` for the call graph.

        Args:
            graph:     The Code Context Graph.
            root:      Starting function name, or None for all roots.
            max_depth: Maximum BFS depth.

        Returns:
            A :class:`Diagram` with Mermaid source.
        """
        import networkx as nx

        nx_g: nx.DiGraph = graph.__dict__.get("_nx", nx.DiGraph())

        call_edges = [
            (u, v)
            for u, v, d in nx_g.edges(data=True)
            if d.get("kind") == EdgeKind.CALLS
        ]

        # Build a sub-graph of call edges only.
        call_g = nx.DiGraph()
        call_g.add_edges_from(call_edges)

        # BFS from roots.
        if root:
            candidates = [n for n in call_g.nodes if n.endswith(f".{root}")]
            start_nodes = candidates[:1] or [root]
        else:
            start_nodes = [n for n in call_g.nodes if call_g.in_degree(n) == 0]

        visited: set[str] = set()
        queue = [(n, 0) for n in start_nodes]
        edges_to_draw: list[tuple[str, str]] = []

        while queue and len(visited) < MAX_DIAGRAM_NODES:
            node, depth = queue.pop(0)
            if node in visited or depth > max_depth:
                continue
            visited.add(node)
            for succ in call_g.successors(node):
                edges_to_draw.append((node, succ))
                queue.append((succ, depth + 1))

        lines: list[str] = ["graph TD"]
        for src, tgt in edges_to_draw[:40]:
            src_label = self._to_mermaid_id(src.split(".")[-1])
            tgt_label = self._to_mermaid_id(tgt.split(".")[-1])
            if src_label and tgt_label:
                lines.append(f"    {src_label} --> {tgt_label}")

        if len(lines) == 1:
            lines.append("    note[No call relationships found]")

        content = "\n".join(lines)
        return Diagram(
            title="Call Graph",
            format=DiagramFormat.MERMAID,
            content=content,
            caption="Function call relationships (top-down).",
        )

    def module_dependency_graph(self, graph: CodeContextGraph) -> Diagram:
        """Generate a Mermaid ``graph LR`` for inter-module imports.

        Args:
            graph: The Code Context Graph.

        Returns:
            A :class:`Diagram` with Mermaid source.
        """
        import_edges = [
            e for e in graph.edges if e.kind == EdgeKind.IMPORTS
        ][:MAX_DIAGRAM_NODES]

        lines: list[str] = ["graph LR"]
        seen: set[tuple[str, str]] = set()
        for edge in import_edges:
            src = self._to_mermaid_id(edge.source_id.split(".")[-1])
            tgt = self._to_mermaid_id(edge.target_id.split(".")[-1] or edge.target_id)
            if src and tgt and (src, tgt) not in seen:
                lines.append(f"    {src} --> {tgt}")
                seen.add((src, tgt))

        if len(lines) == 1:
            lines.append("    note[No import relationships found]")

        content = "\n".join(lines)
        return Diagram(
            title="Module Dependencies",
            format=DiagramFormat.MERMAID,
            content=content,
            caption="Inter-module import relationships.",
        )

    @staticmethod
    def _to_mermaid_id(name: str) -> str:
        """Sanitise a name for use as a Mermaid node ID."""
        clean = re.sub(r"[^a-zA-Z0-9_]", "_", name)
        return clean[:60] if clean else "unknown"
