"""
tests/test_repo_mapper.py
~~~~~~~~~~~~~~~~~~~~~~~~~
Unit tests for the Repo Mapper agent.
"""
from __future__ import annotations

import pytest

from agentic_codebase_reader.agents.repo_mapper import RepoMapper


class TestBuildFileTree:
    """Tests for RepoMapper.build_file_tree."""

    @pytest.mark.xfail(reason="Not yet implemented")
    def test_returns_file_tree_model(self, tmp_path):
        """build_file_tree should return a FileTree with a populated root node."""
        raise NotImplementedError

    @pytest.mark.xfail(reason="Not yet implemented")
    def test_ignores_git_directory(self, tmp_path):
        """build_file_tree should exclude .git from the tree."""
        raise NotImplementedError

    @pytest.mark.xfail(reason="Not yet implemented")
    def test_ignores_pycache(self, tmp_path):
        """build_file_tree should exclude __pycache__ directories."""
        raise NotImplementedError

    @pytest.mark.xfail(reason="Not yet implemented")
    def test_detects_language(self, tmp_path):
        """FileNode for a .py file should have language='Python'."""
        raise NotImplementedError


class TestSummarizeReadme:
    """Tests for RepoMapper.summarize_readme."""

    @pytest.mark.xfail(reason="Not yet implemented")
    async def test_returns_string_summary(self, tmp_path):
        """summarize_readme should return a non-empty string."""
        raise NotImplementedError

    @pytest.mark.xfail(reason="Not yet implemented")
    async def test_returns_empty_when_no_readme(self, tmp_path):
        """summarize_readme should return '' if no README is found."""
        raise NotImplementedError
