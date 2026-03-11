"""
models/file_tree.py
~~~~~~~~~~~~~~~~~~~
Data models representing the repository's file-tree structure.
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Whether a tree node is a file or directory."""

    FILE = "file"
    DIRECTORY = "directory"


class FileNode(BaseModel):
    """A single node (file or directory) in the repository tree.

    Attributes:
        name:      The file or directory name (not the full path).
        path:      Path relative to the repository root.
        node_type: FILE or DIRECTORY.
        size:      File size in bytes (None for directories).
        language:  Detected programming language (None if unknown/directory).
        children:  Child nodes (populated for directories).
    """

    name: str
    path: Path
    node_type: NodeType
    size: int | None = None
    language: str | None = None
    children: list[FileNode] = Field(default_factory=list)

    model_config = {"arbitrary_types_allowed": True}


class FileTree(BaseModel):
    """The complete file-tree of a cloned repository.

    Attributes:
        repo_name:    Name derived from the repository URL.
        repo_url:     The original GitHub URL.
        root:         Root FileNode (directory) containing all children.
        total_files:  Count of all files (excluding ignored paths).
        languages:    Mapping of language → file count.
    """

    repo_name: str
    repo_url: str
    root: FileNode
    total_files: int = 0
    languages: dict[str, int] = Field(default_factory=dict)
