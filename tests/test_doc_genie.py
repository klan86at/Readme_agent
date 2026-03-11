"""
tests/test_doc_genie.py
~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the DocGenie agent.
"""
from __future__ import annotations

import pytest

from agentic_codebase_reader.agents.doc_genie import DocGenie


class TestGenerateDocs:
    """Tests for DocGenie.generate_docs."""

    @pytest.mark.xfail(reason="Not yet implemented")
    async def test_returns_doc_report(self):
        """generate_docs should return a DocReport instance."""
        raise NotImplementedError

    @pytest.mark.xfail(reason="Not yet implemented")
    async def test_includes_standard_sections(self):
        """Generated report should contain all standard section headings."""
        raise NotImplementedError

    @pytest.mark.xfail(reason="Not yet implemented")
    async def test_includes_mermaid_diagram(self):
        """Report should include at least one Mermaid diagram."""
        raise NotImplementedError


class TestSaveDocs:
    """Tests for DocGenie.save_docs."""

    @pytest.mark.xfail(reason="Not yet implemented")
    def test_creates_output_file(self, tmp_path):
        """save_docs should create outputs/<repo_name>/docs.md."""
        raise NotImplementedError
