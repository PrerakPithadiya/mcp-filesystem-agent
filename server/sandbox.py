"""
Sandbox security module for MCP Filesystem.
Ensures that all file operations are strictly confined within the designated workspace directory.
Prevents directory traversal attacks (e.g. '../../', absolute paths, escaping symlinks).
"""

import os
from pathlib import Path
from typing import Optional

DEFAULT_WORKSPACE_NAME = "mcp-workspace"


def get_default_workspace() -> Path:
    """Returns the default workspace directory located in the project root or configured by WORKSPACE_DIR."""
    env_root = os.environ.get("WORKSPACE_DIR")
    if env_root:
        workspace = Path(env_root).resolve()
    else:
        project_root = Path(__file__).resolve().parent.parent
        workspace = project_root / DEFAULT_WORKSPACE_NAME
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def get_safe_path(user_path: str, workspace_root: Optional[Path] = None) -> Path:
    """
    Validates and resolves a user-provided path within the safe workspace directory.

    Args:
        user_path: Relative or requested path from user/LLM.
        workspace_root: Base workspace directory (defaults to get_default_workspace()).

    Returns:
        Path: Canonical resolved Path inside the workspace.

    Raises:
        PermissionError: If the path attempts to escape the workspace.
        ValueError: If user_path is empty or invalid.
    """
    if not user_path or not str(user_path).strip():
        raise ValueError("Path cannot be empty.")

    if workspace_root is None:
        workspace_root = get_default_workspace()
    else:
        workspace_root = workspace_root.resolve()
        workspace_root.mkdir(parents=True, exist_ok=True)

    cleaned_str = str(user_path).strip().replace("\\", "/")

    # Prevent absolute root prefixes like "/foo" from escaping when joined
    while cleaned_str.startswith("/"):
        cleaned_str = cleaned_str[1:]

    target_path = (workspace_root / cleaned_str).resolve()

    # Strict containment check
    try:
        target_path.relative_to(workspace_root)
    except ValueError:
        raise PermissionError(
            f"Security Violation: Target path '{user_path}' attempts to access files outside the safe workspace."
        )

    return target_path
