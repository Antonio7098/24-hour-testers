"""Utility helpers for working with external processes."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def normalize_path(path: str | Path) -> str:
    """Normalize a path for consistent comparison.

    Applies expanduser() and resolve() to handle:
    - ~ expansion
    - Symlink resolution
    - Relative path resolution
    - Case normalization (on case-insensitive systems)

    Returns the normalized path as a string, or the original if normalization fails.
    """
    try:
        return str(Path(path).expanduser().resolve())
    except Exception:
        return str(path)


def paths_equal(path1: str | Path, path2: str | Path) -> bool:
    """Compare two paths for equality after normalization.

    Handles:
    - Different path separators
    - Trailing slashes
    - Symlinks
    - ~ expansion
    - Relative vs absolute paths
    """
    return normalize_path(path1) == normalize_path(path2)


def resolve_executable(command: str) -> str:
    """Resolve an executable command name to an absolute path.

    Raises FileNotFoundError if the command cannot be located or is not executable.
    """
    if not command:
        raise FileNotFoundError("Runtime command is empty")

    path = None

    # Absolute or relative path provided
    if os.path.sep in command or command.startswith("."):
        candidate = Path(command).expanduser().resolve()
        if not candidate.exists():
            raise FileNotFoundError(f"Runtime command not found: {candidate}")
        if not os.access(candidate, os.X_OK):
            raise FileNotFoundError(f"Runtime command is not executable: {candidate}")
        path = str(candidate)
    else:
        which = shutil.which(command)
        if not which:
            raise FileNotFoundError(f"Runtime command '{command}' not found on PATH")
        path = which

    return path
