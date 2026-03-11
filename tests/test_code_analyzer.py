"""
tests/test_code_analyzer.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the Code Analyzer agent.
"""
from __future__ import annotations

import pytest

from agentic_codebase_reader.agents.code_analyzer import CodeAnalyzer


class TestBuildCodeGraph:
    """Tests for CodeAnalyzer.build_code_graph."""

    @pytest.mark.xfail(reason="Not yet implemented")
    def test_returns_code_context_graph(self, tmp_path):
        """build_code_graph should return a CodeContextGraph instance."""
        raise NotImplementedError

    @pytest.mark.xfail(reason="Not yet implemented")
    def test_extracts_function_nodes(self, tmp_path):
        """Parsed Python file should produce SymbolNode entries for functions."""
        raise NotImplementedError

    @pytest.mark.xfail(reason="Not yet implemented")
    def test_extracts_class_nodes(self, tmp_path):
        """Parsed Python file should produce SymbolNode entries for classes."""
        raise NotImplementedError

    @pytest.mark.xfail(reason="Not yet implemented")
    def test_extracts_call_edges(self, tmp_path):
        """Call relationships should appear as CALLS edges in the graph."""
        raise NotImplementedError

    @pytest.mark.xfail(reason="Not yet implemented")
    def test_extracts_inheritance_edges(self, tmp_path):
        """Inheritance should appear as INHERITS edges in the graph."""
        raise NotImplementedError


class TestQueryGraph:
    """Tests for CodeAnalyzer.query_graph."""

    @pytest.mark.xfail(reason="Not yet implemented")
    def test_callers_of_returns_list(self):
        """callers_of should return a list of SymbolNode."""
        raise NotImplementedError
