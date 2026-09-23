"""
Sandbox security module for MCP Filesystem.
Ensures that all file operations are strictly confined within the designated workspace directory.
Prevents directory traversal attacks (e.g. '../../', absolute paths, escaping symlinks).
"""

import os
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)

DEFAULT_WORKSPACE_NAME = "mcp-workspace"


def get_default_workspace() -> Path:
    """Returns the default workspace directory located in the project root or configured by WORKSPACE_DIR."""
    env_root = os.environ.get("WORKSPACE_DIR")
    if env_root:
        workspace = Path(env_root).resolve()
    else:
        workspace = PROJECT_ROOT / DEFAULT_WORKSPACE_NAME
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

    raw_str = str(user_path).strip()

    # Check if the user specified an absolute path (POSIX root /..., Windows drive C:\..., or UNC \\...)
    if raw_str.startswith(("/", "\\")) or (len(raw_str) > 1 and raw_str[1] == ":"):
        try:
            target_path = Path(raw_str).resolve()
            target_path.relative_to(workspace_root)
            return target_path
        except (ValueError, Exception):
            raise PermissionError(
                f"Security Violation: Target path '{user_path}' attempts to access files outside the safe workspace."
            )

    cleaned_str = raw_str.replace("\\", "/")

    # If the user/LLM prefixed the workspace root folder name (e.g. 'Desktop/test.txt' or 'mcp-workspace/test.txt'),
    # strip it so we don't accidentally create a nested folder like 'Desktop/Desktop/test.txt'.
    root_name = workspace_root.name.lower()
    if cleaned_str.lower().startswith(root_name + "/"):
        cleaned_str = cleaned_str[len(root_name) + 1:]
    elif cleaned_str.lower() == root_name:
        cleaned_str = "."

    target_path = (workspace_root / cleaned_str).resolve()

    # Strict containment check
    try:
        target_path.relative_to(workspace_root)
    except ValueError:
        raise PermissionError(
            f"Security Violation: Target path '{user_path}' attempts to access files outside the safe workspace."
        )

    return target_path
