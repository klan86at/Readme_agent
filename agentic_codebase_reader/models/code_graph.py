"""
models/code_graph.py
~~~~~~~~~~~~~~~~~~~~
Data models for the Code Context Graph (CCG).

The CCG captures relationships between functions, classes, and modules:
  - Function calls (A calls B)
  - Class inheritance (Child extends Parent)
  - Composition / attribute references
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class SymbolKind(str, Enum):
    """The kind of a symbol node in the graph."""

    FUNCTION = "function"
    CLASS = "class"
    METHOD = "method"
    MODULE = "module"


class EdgeKind(str, Enum):
    """The type of relationship between two symbols."""

    CALLS = "calls"
    INHERITS = "inherits"
    COMPOSES = "composes"
    IMPORTS = "imports"
    DEFINES = "defines"


class SymbolNode(BaseModel):
    """A symbol (function, class, module) in the Code Context Graph.

    Attributes:
        id:          Unique identifier: "<module>.<SymbolName>".
        name:        Short symbol name (e.g. "train_model").
        kind:        FUNCTION, CLASS, METHOD, or MODULE.
        file_path:   Absolute path to the source file.
        start_line:  First line of the symbol's definition.
        end_line:    Last line of the symbol's definition.
        docstring:   Extracted docstring (if any).
        signature:   Full signature string (e.g. "def train_model(data, lr=1e-3)").
    """

    id: str
    name: str
    kind: SymbolKind
    file_path: Path
    start_line: int
    end_line: int
    docstring: str | None = None
    signature: str | None = None

    model_config = {"arbitrary_types_allowed": True}


class GraphEdge(BaseModel):
    """A directed edge in the Code Context Graph.

    Attributes:
        source_id: ID of the source SymbolNode.
        target_id: ID of the target SymbolNode.
        kind:      The type of relationship.
    """

    source_id: str
    target_id: str
    kind: EdgeKind


class CodeContextGraph(BaseModel):
    """The full Code Context Graph for a repository.

    Attributes:
        repo_name: Name of the repository.
        nodes:     All symbol nodes in the graph.
        edges:     All directed edges between nodes.
    """

    repo_name: str
    nodes: list[SymbolNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)

    def get_node(self, node_id: str) -> SymbolNode | None:
        """Return the node with the given ID, or None if not found."""
        raise NotImplementedError

    def callers_of(self, function_name: str) -> list[SymbolNode]:
        """Return all nodes that call the given function name."""
        raise NotImplementedError

    def callees_of(self, function_name: str) -> list[SymbolNode]:
        """Return all nodes called by the given function name."""
        raise NotImplementedError

    def subclasses_of(self, class_name: str) -> list[SymbolNode]:
        """Return all nodes that inherit from the given class name."""
        raise NotImplementedError
