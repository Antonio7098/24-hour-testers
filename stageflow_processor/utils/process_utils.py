"""Utility helpers for working with external processes."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


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
