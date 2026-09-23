"""
Diff calculation utility using Python's standard difflib.
Computes line-by-line structured diffs with line numbering and addition/deletion stats.
"""

import difflib
from typing import Any, Dict, List, Optional


def compute_file_diff(old_content: str, new_content: str, file_path: str) -> Dict[str, Any]:
    """Compute structured line diff between old_content and new_content.

    Returns:
        dict with:
            - file_path: str
            - stats: {"added": int, "deleted": int}
            - lines: list of {"type": "context" | "add" | "delete", "old_num": int|None, "new_num": int|None, "content": str}
    """
    old_lines = old_content.splitlines() if old_content else []
    new_lines = new_content.splitlines() if new_content else []

    if not old_lines and new_lines:
        lines = [
            {"type": "add", "old_num": None, "new_num": idx + 1, "content": line}
            for idx, line in enumerate(new_lines)
        ]
        return {
            "file_path": file_path,
            "stats": {"added": len(new_lines), "deleted": 0},
            "lines": lines,
        }

    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    diff_lines: List[Dict[str, Any]] = []
    added_count = 0
    deleted_count = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                diff_lines.append({
                    "type": "context",
                    "old_num": i1 + offset + 1,
                    "new_num": j1 + offset + 1,
                    "content": old_lines[i1 + offset],
                })
        elif tag == "delete":
            for offset in range(i2 - i1):
                diff_lines.append({
                    "type": "delete",
                    "old_num": i1 + offset + 1,
                    "new_num": None,
                    "content": old_lines[i1 + offset],
                })
                deleted_count += 1
        elif tag == "insert":
            for offset in range(j2 - j1):
                diff_lines.append({
                    "type": "add",
                    "old_num": None,
                    "new_num": j1 + offset + 1,
                    "content": new_lines[j1 + offset],
                })
                added_count += 1
        elif tag == "replace":
            for offset in range(i2 - i1):
                diff_lines.append({
                    "type": "delete",
                    "old_num": i1 + offset + 1,
                    "new_num": None,
                    "content": old_lines[i1 + offset],
                })
                deleted_count += 1
            for offset in range(j2 - j1):
                diff_lines.append({
                    "type": "add",
                    "old_num": None,
                    "new_num": j1 + offset + 1,
                    "content": new_lines[j1 + offset],
                })
                added_count += 1

    return {
        "file_path": file_path,
        "stats": {"added": added_count, "deleted": deleted_count},
        "lines": diff_lines,
    }
