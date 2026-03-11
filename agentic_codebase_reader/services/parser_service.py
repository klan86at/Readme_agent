"""
services/parser_service.py
~~~~~~~~~~~~~~~~~~~~~~~~~~
Tree-sitter wrapper service — lazy parser initialisation and AST helpers.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Mapping from file extension → Tree-sitter language module attribute name.
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
}

# Human-readable names for display in FileNode.language.
LANGUAGE_DISPLAY: dict[str, str] = {
    "python": "Python",
    "javascript": "JavaScript",
    "typescript": "TypeScript",
    "go": "Go",
    "rust": "Rust",
    "java": "Java",
    "cpp": "C++",
    "c": "C",
}


class ParserServiceError(Exception):
    """Raised when a file cannot be parsed."""


class ParserService:
    """Manages Tree-sitter parsers and provides high-level parse utilities."""

    def __init__(self) -> None:
        self._parsers: dict[str, Any] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def parse(self, file_path: Path) -> tuple[Any, bytes]:
        """Parse a source file and return (tree, source_bytes).

        Args:
            file_path: Absolute path to a source file.

        Returns:
            A tuple of (Tree-sitter Tree, raw source bytes).

        Raises:
            ValueError: If the file extension is not supported.
            OSError:    If the file cannot be read.
        """
        ext = file_path.suffix.lower()
        lang = EXTENSION_TO_LANGUAGE.get(ext)
        if lang is None:
            raise ValueError(
                f"Unsupported file extension {ext!r} for {file_path}"
            )

        source = file_path.read_bytes()
        parser = self._get_parser(lang)
        tree = parser.parse(source)
        return tree, source

    def extract_functions(
        self, tree: Any, source: bytes
    ) -> list[dict[str, Any]]:
        """Extract function/method definitions from a syntax tree.

        Returns a list of dicts with keys:
        ``name``, ``start_line``, ``end_line``, ``docstring``, ``signature``.
        """
        results: list[dict[str, Any]] = []
        self._walk(tree.root_node, source, results, target_types={
            "function_definition",   # Python
            "function_declaration",  # JS/TS/Go
            "method_declaration",    # Java/Go
        })
        return results

    def extract_classes(
        self, tree: Any, source: bytes
    ) -> list[dict[str, Any]]:
        """Extract class definitions from a syntax tree.

        Returns a list of dicts with keys:
        ``name``, ``bases``, ``start_line``, ``end_line``, ``docstring``.
        """
        results: list[dict[str, Any]] = []
        self._walk(tree.root_node, source, results, target_types={
            "class_definition",   # Python
            "class_declaration",  # Java/TS
        }, is_class=True)
        return results

    def extract_calls(
        self, tree: Any, source: bytes
    ) -> list[dict[str, Any]]:
        """Extract function-call expressions from a syntax tree.

        Returns a list of dicts with keys: ``callee_name``, ``line``.
        """
        calls: list[dict[str, Any]] = []
        self._collect_calls(tree.root_node, source, calls)
        return calls

    def extract_imports(
        self, tree: Any, source: bytes
    ) -> list[dict[str, Any]]:
        """Extract import statements from a syntax tree.

        Returns a list of dicts with keys: ``module``, ``names``, ``line``.
        """
        imports: list[dict[str, Any]] = []
        self._collect_imports(tree.root_node, source, imports)
        return imports

    @staticmethod
    def detect_language(file_path: Path) -> str | None:
        """Return a human-readable language name for a given file path.

        Args:
            file_path: Path to the file.

        Returns:
            E.g. ``"Python"``, ``"JavaScript"``, or ``None``.
        """
        lang_key = EXTENSION_TO_LANGUAGE.get(file_path.suffix.lower())
        return LANGUAGE_DISPLAY.get(lang_key, None) if lang_key else None

    # ── Private helpers ───────────────────────────────────────────────────────

    def _get_parser(self, language: str) -> Any:
        """Lazily initialise and cache a Tree-sitter parser."""
        if language in self._parsers:
            return self._parsers[language]

        try:
            import tree_sitter_python as tspython
            from tree_sitter import Language, Parser
        except ImportError as exc:
            raise ImportError(
                "tree-sitter and tree-sitter-python must be installed. "
                "Run: uv pip install tree-sitter tree-sitter-python"
            ) from exc

        if language == "python":
            lang_obj = Language(tspython.language())
            parser = Parser(lang_obj)
            self._parsers[language] = parser
            return parser

        # For other languages, attempt a generic dynamic load.
        try:
            import importlib
            mod = importlib.import_module(f"tree_sitter_{language}")
            lang_obj = Language(mod.language())
            parser = Parser(lang_obj)
            self._parsers[language] = parser
            return parser
        except (ImportError, AttributeError) as exc:
            raise ValueError(
                f"No tree-sitter language module found for {language!r}. "
                f"Install tree-sitter-{language}."
            ) from exc

    def _walk(
        self,
        node: Any,
        source: bytes,
        results: list[dict[str, Any]],
        target_types: set[str],
        is_class: bool = False,
    ) -> None:
        """Recursively walk an AST and collect nodes matching target_types."""
        if node.type in target_types:
            name_node = node.child_by_field_name("name")
            name = (
                source[name_node.start_byte: name_node.end_byte].decode()
                if name_node else "<anonymous>"
            )
            entry: dict[str, Any] = {
                "name": name,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "docstring": self._extract_docstring(node, source),
                "signature": source[
                    node.start_byte: node.start_byte
                    + min(200, node.end_byte - node.start_byte)
                ].decode(errors="replace").split("\n")[0],
            }
            if is_class:
                entry["bases"] = self._extract_bases(node, source)
            results.append(entry)

        for child in node.children:
            self._walk(child, source, results, target_types, is_class)

    def _collect_calls(
        self,
        node: Any,
        source: bytes,
        calls: list[dict[str, Any]],
    ) -> None:
        """Recursively collect call_expression nodes."""
        if node.type == "call":
            func_node = node.child_by_field_name("function")
            if func_node:
                callee = source[
                    func_node.start_byte: func_node.end_byte
                ].decode(errors="replace")
                # Keep only simple names / attr access (skip complex exprs)
                if len(callee) < 120:
                    calls.append({
                        "callee_name": callee,
                        "line": node.start_point[0] + 1,
                    })
        for child in node.children:
            self._collect_calls(child, source, calls)

    def _collect_imports(
        self,
        node: Any,
        source: bytes,
        imports: list[dict[str, Any]],
    ) -> None:
        """Recursively collect import statement nodes (Python)."""
        if node.type in ("import_statement", "import_from_statement"):
            raw = source[node.start_byte: node.end_byte].decode(errors="replace")
            imports.append({
                "raw": raw.strip(),
                "line": node.start_point[0] + 1,
            })
        for child in node.children:
            self._collect_imports(child, source, imports)

    @staticmethod
    def _extract_docstring(node: Any, source: bytes) -> str | None:
        """Extract a Python-style docstring from a function/class node body."""
        body = node.child_by_field_name("body")
        if body is None:
            return None
        for child in body.children:
            if child.type == "expression_statement":
                for sub in child.children:
                    if sub.type == "string":
                        raw = source[sub.start_byte: sub.end_byte].decode(
                            errors="replace"
                        )
                        return raw.strip('"""').strip("'''").strip('"').strip("'").strip()
        return None

    @staticmethod
    def _extract_bases(node: Any, source: bytes) -> list[str]:
        """Extract base class names from a class_definition node."""
        bases: list[str] = []
        arg_list = node.child_by_field_name("superclasses")
        if arg_list:
            for child in arg_list.children:
                if child.type not in (",", "(", ")", "argument_list"):
                    bases.append(
                        source[child.start_byte: child.end_byte].decode(
                            errors="replace"
                        )
                    )
        return [b.strip() for b in bases if b.strip()]
