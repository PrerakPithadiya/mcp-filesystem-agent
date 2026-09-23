"""
MCP Filesystem Server
Implements 6 core filesystem tools under strict sandboxing using FastMCP.
"""

import os
import shutil
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

try:
    from server.sandbox import get_default_workspace, get_safe_path
except ModuleNotFoundError:
    from sandbox import get_default_workspace, get_safe_path

# Initialize FastMCP Server
mcp = FastMCP("mcp-filesystem")

# OS protected system files that must never be created, overwritten, or deleted
PROTECTED_SYSTEM_FILES = {"desktop.ini", "thumbs.db", "$recycle.bin", ".ds_store"}


@mcp.tool()
def create_folder(folder_path: str) -> str:
    """Create a new folder/directory inside the safe workspace.

    Args:
        folder_path: Relative path of the folder to create (e.g. 'Projects' or 'docs/api').

    Returns:
        Confirmation message.
    """
    try:
        target = get_safe_path(folder_path)
        if target.exists():
            if target.is_dir():
                return f"Folder already exists: '{folder_path}'"
            return f"Error: A file already exists at '{folder_path}'"

        target.mkdir(parents=True, exist_ok=True)
        return f"Successfully created folder: '{folder_path}'"
    except Exception as e:
        return f"Failed to create folder '{folder_path}': {str(e)}"


@mcp.tool()
def create_file(file_path: str, content: str = "") -> str:
    """Create a new text file with content inside the safe workspace.

    Args:
        file_path: Relative path of the file to create (e.g. 'notes.txt' or 'Projects/app.py').
        content: Text content to write into the new file.

    Returns:
        Confirmation message.
    """
    try:
        target = get_safe_path(file_path)
        if target.name.lower() in PROTECTED_SYSTEM_FILES:
            return f"Error: Cannot create or overwrite protected system file '{target.name}'"

        if target.exists():
            return f"Error: File already exists at '{file_path}'. Use update_file to modify existing files."

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Successfully created file: '{file_path}' ({len(content)} characters)"
    except Exception as e:
        return f"Failed to create file '{file_path}': {str(e)}"


@mcp.tool()
def read_file(file_path: str) -> str:
    """Read and display the text content of a file inside the safe workspace.

    Args:
        file_path: Relative path of the file to read (e.g. 'notes.txt').

    Returns:
        File contents or error message.
    """
    try:
        target = get_safe_path(file_path)
        if not target.exists():
            return f"Error: File not found: '{file_path}'"
        if not target.is_file():
            return f"Error: '{file_path}' is a directory, not a file."

        file_size = target.stat().st_size
        max_preview_bytes = 250_000

        try:
            # Check for binary file by reading a header chunk
            with target.open("rb") as bf:
                chunk = bf.read(1024)
                if b"\x00" in chunk:
                    return f"Error: '{file_path}' is a binary file and cannot be read as plain text."

            if file_size > max_preview_bytes:
                with target.open("r", encoding="utf-8", errors="replace") as f:
                    content = f.read(max_preview_bytes)
                return content + f"\n\n... [Content truncated: file size is {file_size:,} bytes, showing first {max_preview_bytes:,} bytes]"
            else:
                return target.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return f"Error: '{file_path}' is a binary file and cannot be read as plain text."
    except Exception as e:
        return f"Failed to read file '{file_path}': {str(e)}"


@mcp.tool()
def list_folder(folder_path: str = "") -> str:
    """List the files and subfolders inside a folder in the safe workspace.

    Args:
        folder_path: Relative path of the folder to list. Leave empty or use '.' for workspace root.

    Returns:
        Formatted list of files and folders with sizes.
    """
    try:
        if not folder_path or folder_path.strip() in (".", "/"):
            target = get_default_workspace()
            display_name = "(workspace root)"
        else:
            target = get_safe_path(folder_path)
            display_name = folder_path

        if not target.exists():
            return f"Error: Folder does not exist: '{folder_path}'"
        if not target.is_dir():
            return f"Error: '{folder_path}' is a file, not a directory."

        entries = sorted(
            [p for p in target.iterdir() if p.name.lower() not in PROTECTED_SYSTEM_FILES],
            key=lambda p: (not p.is_dir(), p.name.lower())
        )
        if not entries:
            return f"Folder '{display_name}' is empty."

        lines = [f"Contents of '{display_name}':"]
        for entry in entries:
            if entry.is_dir():
                try:
                    num_items = len([c for c in entry.iterdir() if c.name.lower() not in PROTECTED_SYSTEM_FILES])
                except Exception:
                    num_items = 0
                lines.append(f"📁 [DIR]  {entry.name}/ ({num_items} items)")
            else:
                size_bytes = entry.stat().st_size
                lines.append(f"📄 [FILE] {entry.name} ({size_bytes} bytes)")

        return "\n".join(lines)
    except Exception as e:
        return f"Failed to list folder '{folder_path}': {str(e)}"


@mcp.tool()
def update_file(file_path: str, content: str, mode: Literal["overwrite", "append"] = "overwrite") -> str:
    """Update or append content to an existing file in the safe workspace.

    Args:
        file_path: Relative path of the file to update.
        content: The text content to write or append.
        mode: Either 'overwrite' to replace content, or 'append' to add to the end. Defaults to 'overwrite'.

    Returns:
        Confirmation message.
    """
    try:
        target = get_safe_path(file_path)
        if target.name.lower() in PROTECTED_SYSTEM_FILES:
            return f"Error: Cannot modify protected system file '{target.name}'"

        if not target.exists():
            return f"Error: File does not exist at '{file_path}'. Use create_file to create new files."
        if not target.is_file():
            return f"Error: '{file_path}' is a directory, not a file."

        if mode == "append":
            current = target.read_text(encoding="utf-8")
            new_content = current + ("\n" if not current.endswith("\n") and current else "") + content
            target.write_text(new_content, encoding="utf-8")
            return f"Successfully appended to '{file_path}'. New size: {len(new_content)} characters."
        else:
            target.write_text(content, encoding="utf-8")
            return f"Successfully updated '{file_path}'. Written {len(content)} characters."
    except Exception as e:
        return f"Failed to update file '{file_path}': {str(e)}"


@mcp.tool()
def delete_item(path: str, recursive: bool = False) -> str:
    """Delete a file or folder from the safe workspace.
    To delete all items or clear the workspace, use path='everything' or path='*'.
    NOTE: This action is permanent and should only be called after explicit user confirmation.

    Args:
        path: Relative path of the file or folder to delete, or 'everything' / '*' to delete all items.
        recursive: Required to be True when deleting a non-empty folder.

    Returns:
        Confirmation message.
    """
    try:
        norm_path = str(path).strip().lower()
        if norm_path in ("everything", "*", "all", "all items", "workspace", "workshop", "."):
            workspace = get_default_workspace()
            deleted_items = []
            for item in list(workspace.iterdir()):
                if item.name.lower() in PROTECTED_SYSTEM_FILES:
                    continue
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                    deleted_items.append(item.name)
                except Exception as ex:
                    deleted_items.append(f"{item.name} (failed: {ex})")
            if deleted_items:
                return f"Successfully deleted all {len(deleted_items)} items in workspace: {', '.join(deleted_items)}"
            return "Workspace is already empty."

        target = get_safe_path(path)
        if target.name.lower() in PROTECTED_SYSTEM_FILES:
            return f"Error: Cannot delete protected system file '{target.name}'"

        if not target.exists():
            return f"Error: Path does not exist: '{path}'"

        if target.is_file():
            target.unlink()
            return f"Successfully deleted file: '{path}'"
        elif target.is_dir():
            has_children = any(target.iterdir())
            if has_children and not recursive:
                return f"Error: Folder '{path}' is not empty. Set recursive=True to delete folder and all its contents."
            try:
                if not has_children:
                    target.rmdir()
                else:
                    shutil.rmtree(target)
            except PermissionError:
                import stat
                def _handle_readonly(func, file_path, exc_info):
                    try:
                        os.chmod(file_path, stat.S_IWRITE)
                        func(file_path)
                    except Exception:
                        pass
                shutil.rmtree(target, onexc=_handle_readonly)
            return f"Successfully deleted folder: '{path}'"
        else:
            return f"Error: Unknown item type at '{path}'"
    except Exception as e:
        return f"Failed to delete '{path}': {str(e)}"


if __name__ == "__main__":
    # When run directly, start stdio transport
    mcp.run(transport="stdio")
