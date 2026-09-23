"""
Offline Handler Module for MCP Filesystem.

Provides:
1. Robust network/DNS error detection (e.g. [Errno 11001] getaddrinfo failed).
2. Local offline intent parser for basic and multi-item filesystem operations.
3. Offline request executor executing operations locally via MCP tools with
   the same safety sandboxing and confirmation gates.
"""

import logging
import re
import socket
import uuid
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("offline_handler")


def is_network_error(exc: Any) -> bool:
    """
    Returns True if an exception represents a network or DNS resolution failure
    (such as Winsock 11001 getaddrinfo failure, offline status, or connection drop).
    """
    if exc is None:
        return False

    # Check direct socket exception types
    if isinstance(exc, (socket.gaierror, socket.herror, ConnectionRefusedError, ConnectionResetError, TimeoutError)):
        return True

    err_str = str(exc).lower()

    # Common network/DNS failure signatures
    network_signatures = [
        "11001",
        "getaddrinfo",
        "nameresolutionerror",
        "gaierror",
        "name resolution",
        "failed to resolve",
        "network is unreachable",
        "connection refused",
        "connection reset",
        "connecterror",
        "networkerror",
        "newconnectionerror",
        "endpoint_url",
        "nodename nor servname provided",
        "host_not_found",
        "wsaerror",
        "wsahost_not_found",
        "temporary failure in name resolution",
        "connect timeout",
        "timed out",
    ]

    return any(sig in err_str for sig in network_signatures)


def _resolve_target_from_history(history: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    """Finds the most recently mentioned file or folder in conversation history."""
    if not history:
        return None

    # Inspect from most recent message backwards
    for item in reversed(history):
        content = item.get("content", "")
        if not content:
            continue

        # Look for explicit tool result mentions e.g. "file: foo.txt" or "folder: bar"
        m = re.search(r"(?:file|folder|item|path)\s*[:]?\s*['\"]?([a-zA-Z0-9_\-\.\/]+)['\"]?", content, re.IGNORECASE)
        if m:
            candidate = m.group(1).strip().strip("'\"")
            if candidate and candidate.lower() not in ("it", "that", "this"):
                return candidate

        # Look for words with file extensions (e.g. notes.txt, app.py, budget.xlsx)
        ext_match = re.findall(r"\b([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]{1,6})\b", content)
        if ext_match:
            return ext_match[-1]

        # Look for folder names mentioned after folder
        f_match = re.search(r"folder\s+(?:called|named)?\s*['\"]?([a-zA-Z0-9_\-]+)['\"]?", content, re.IGNORECASE)
        if f_match:
            return f_match.group(1).strip()

    return None


def parse_offline_intent(user_message: str, history: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
    """
    Parses a user's natural language command into a structured filesystem action
    when running in local offline fallback mode.
    Returns None if the message is conversational or ambiguous.
    """
    msg = user_message.strip()
    msg_lower = msg.lower()

    if not msg:
        return None

    # Common greetings and non-filesystem queries
    conversational_patterns = [
        r"^(hey+|hi+|hello+|howdy|greetings|hola|good\s+(morning|afternoon|evening))\b",
        r"^how\s+are\s+you",
        r"^who\s+are\s+you",
        r"^what\s+can\s+you\s+do",
        r"^tell\s+me\s+a\s+joke",
        r"^thanks?(\s+you)?\b",
        r"^what\s+is\b",
        r"^why\b",
        r"^help\b",
    ]
    for pat in conversational_patterns:
        if re.search(pat, msg_lower):
            # Exception: "help list files" or "what files are here"
            if not any(k in msg_lower for k in ["folder", "file", "workspace", "read", "create", "delete", "list", "dir", "ls"]):
                return None

    # --- Pronoun references ("read it", "delete it", "cat it", etc.) ---
    pronoun_read = re.match(r"^(?:read|cat|view|open|show|display)\s+(?:it|that|the\s+file|this)$", msg_lower)
    if pronoun_read:
        target = _resolve_target_from_history(history)
        if target:
            return {"action": "read_file", "file_path": target}

    pronoun_delete = re.match(r"^(?:delete|remove|rm|erase)\s+(?:it|that|the\s+file|the\s+folder|this)$", msg_lower)
    if pronoun_delete:
        target = _resolve_target_from_history(history)
        if target:
            return {"action": "delete_item", "targets": [target], "is_everything": False}

    # --- Shell shorthand: echo "..." > file.txt or >> file.txt ---
    echo_match = re.match(r"^echo\s+['\"]?(.*?)['\"]?\s*(>>|>)\s*([^\s'\"]+|['\"][^'\"]+['\"])$", msg, re.DOTALL)
    if echo_match:
        content = echo_match.group(1)
        operator = echo_match.group(2)
        target = echo_match.group(3).strip().strip("'\"")
        if operator == ">>":
            return {"action": "update_file", "file_path": target, "content": content, "mode": "append"}
        else:
            return {"action": "create_file", "file_path": target, "content": content}

    # --- Shell shorthand: touch file.txt ---
    touch_match = re.match(r"^touch\s+([^\s'\"]+|['\"][^'\"]+['\"])$", msg, re.IGNORECASE)
    if touch_match:
        target = touch_match.group(1).strip().strip("'\"")
        return {"action": "create_file", "file_path": target, "content": ""}

    # --- 1. LIST WORKSPACE / FOLDER ---
    if msg_lower in ("ls", "dir", "list", "files", "list files", "show files", "list all", "list workspace", "show workspace", "what files are here"):
        return {"action": "list_folder", "folder_path": ""}

    list_match = re.search(r"^(?:list|show|view)\s+(?:files|folders|contents|directory)?\s*(?:in|inside|of)?\s*(.*)$", msg_lower)
    if list_match and any(w in msg_lower for w in ["list", "show contents", "show files", "ls", "dir"]):
        target = list_match.group(1).strip().strip("'\"")
        if target in ("workspace", "here", "root", "", ".", "./"):
            target = ""
        return {"action": "list_folder", "folder_path": target}

    # --- 2. CREATE FOLDER(S) ---
    # Patterns like "create a folder called Prerak", "make 3 folder 1. a 2. b 3. c", "create folders x, y and z"
    folder_create_match = re.search(
        r"(?:create|make|add|mkdir|build)\s+(?:a\s+|an\s+|the\s+|\d+\s+)?(?:new\s+)?folders?\s+(?:called|named|name|for)?\s*[:]?\s*(.*)",
        msg,
        re.IGNORECASE,
    )
    if folder_create_match:
        raw_targets = folder_create_match.group(1).strip()
        names = _extract_names_list(raw_targets)
        if names:
            return {"action": "create_folder", "targets": names}

    # Terse: "mkdir Prerak"
    mkdir_match = re.match(r"^mkdir\s+(.+)$", msg, re.IGNORECASE)
    if mkdir_match:
        names = _extract_names_list(mkdir_match.group(1).strip())
        if names:
            return {"action": "create_folder", "targets": names}

    # --- 3. CREATE / TOUCH FILE ---
    # Patterns: "create a file named notes.txt with content '...'"
    file_create_match = re.search(
        r"(?:create|make|write|touch)\s+(?:a\s+|an\s+|the\s+)?(?:new\s+)?file\s+(?:called|named)?\s*[:]?\s*([^\s'\"]+|['\"][^'\"]+['\"])\s*(?:with\s+(?:content|text)?\s*[:]?\s*['\"]?(.*?)['\"]?)?$",
        msg,
        re.IGNORECASE | re.DOTALL,
    )
    if file_create_match:
        file_path = file_create_match.group(1).strip().strip("'\"")
        content = file_create_match.group(2) or ""
        # Clean trailing quote if present
        content = content.rstrip("'\"")
        return {"action": "create_file", "file_path": file_path, "content": content}

    # Shorthand: "notes.txt: buy milk"
    short_file_match = re.match(r"^([a-zA-Z0-9_\-\.\/]+\.[a-zA-Z0-9]+)\s*[:=]\s*(.+)$", msg, re.DOTALL)
    if short_file_match:
        return {
            "action": "create_file",
            "file_path": short_file_match.group(1).strip(),
            "content": short_file_match.group(2).strip(),
        }

    # --- 4. READ FILE ---
    read_match = re.search(
        r"(?:read|cat|view|open|show|display|get)\s+(?:the\s+)?(?:content\s+of\s+)?(?:file\s+)?([^\s'\"]+|['\"][^'\"]+['\"])$",
        msg,
        re.IGNORECASE,
    )
    if read_match and any(k in msg_lower for k in ["read", "cat", "view", "open"]):
        target = read_match.group(1).strip().strip("'\"")
        if target:
            return {"action": "read_file", "file_path": target}

    # --- 5. UPDATE / APPEND TO FILE ---
    append_match = re.search(
        r"(?:append|add)\s+['\"]?(.*?)['\"]?\s+to\s+(?:file\s+)?([^\s'\"]+|['\"][^'\"]+['\"])$",
        msg,
        re.IGNORECASE,
    )
    if append_match:
        content = append_match.group(1).strip()
        file_path = append_match.group(2).strip().strip("'\"")
        return {"action": "update_file", "file_path": file_path, "content": content, "mode": "append"}

    # --- 6. DELETE ITEM(S) ---
    delete_match = re.search(
        r"(?:delete|remove|rm|erase|destroy|wipe)\s+(?:the\s+)?(?:folder|file|directory)?s?\s*(?:called|named)?\s*[:]?\s*(.*)",
        msg,
        re.IGNORECASE,
    )
    if delete_match:
        raw_targets = delete_match.group(1).strip()
        is_everything = any(w in raw_targets.lower() for w in ["everything", "all", "workspace", "workshop", "*"])
        if is_everything:
            return {"action": "delete_item", "targets": ["everything"], "is_everything": True}
        names = _extract_names_list(raw_targets)
        if names:
            return {"action": "delete_item", "targets": names, "is_everything": False}

    return None


def _extract_names_list(text: str) -> List[str]:
    """
    Extracts individual folder/file names from comma-, 'and'-, or numbered-separated text.
    Handles:
    - 'Prerak, Utsav and Umang' -> ['Prerak', 'Utsav', 'Umang']
    - '1. Prerak 2. Utsav 3. Umang' -> ['Prerak', 'Utsav', 'Umang']
    - ''Prerak, Utsav, Umang'' -> ['Prerak', 'Utsav', 'Umang']
    """
    cleaned = text.strip().strip("'\"")
    if not cleaned:
        return []

    # Handle numbered items e.g. "1. Prerak 2. Utsav 3. Umang" or "1: Prerak\n2: Utsav"
    if re.search(r"\b\d+[\.\:\)]\s*", cleaned):
        parts = re.split(r"\s*\b\d+[\.\:\)]\s*", cleaned)
        names = [p.strip().strip("',\"") for p in parts if p.strip()]
        if names:
            return names

    # Split on commas and conjunctions
    # Replace ' and ' with comma
    standardized = re.sub(r"\s+and\s+", ", ", cleaned, flags=re.IGNORECASE)
    parts = standardized.split(",")
    names = [p.strip().strip("',\"") for p in parts if p.strip()]
    return names


async def handle_offline_request(
    intent: Optional[Dict[str, Any]],
    user_message: str,
    pending_confirmations: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Executes an offline request locally via the MCP client service.
    Enforces security sandbox and human-in-the-loop confirmation gates for deletions.
    """
    from backend.llm_agent import _execute_tool_with_diff
    from backend.mcp_client import mcp_client_service

    # Case A: Conversational or unparseable query when offline
    if not intent:
        return {
            "reply": (
                "🌐 **Internet Connection Unavailable (Offline Mode)**\n\n"
                "Unable to connect to Google Gemini API (network or DNS connection is currently unavailable).\n\n"
                "**Local Offline Capabilities:**\n"
                "Your local files and workspace are completely safe! You can execute local filesystem operations without internet:\n"
                "- `create folder <name>` (e.g. `create a folder called Prerak`)\n"
                "- `make folders Prerak, Utsav and Umang`\n"
                "- `create file <name> with content '<text>'`\n"
                "- `read file <name>`\n"
                "- `list files`\n"
                "- `delete <name>`\n\n"
                "*(Once your Wi-Fi or internet connection is restored, full conversational AI will resume automatically.)*"
            ),
            "tool_calls": [],
            "requires_confirmation": False,
        }

    action = intent["action"]
    executed_tools: List[Dict[str, Any]] = []

    # Case B: Create Folder(s)
    if action == "create_folder":
        targets = intent.get("targets", [])
        results = []
        for target in targets:
            args = {"folder_path": target}
            res_str, _ = await _execute_tool_with_diff("create_folder", args)
            status = "success" if not str(res_str).startswith("Error") else "error"
            tool_entry = {
                "name": "create_folder",
                "arguments": args,
                "status": status,
                "result": res_str,
            }
            executed_tools.append(tool_entry)
            results.append(f"- **`{target}`**: {res_str}")

        count = len(targets)
        reply = (
            f"⚡ **Offline Execution Active**\n\n"
            f"Successfully processed {count} folder creation{'s' if count > 1 else ''} locally via MCP:\n"
            + "\n".join(results)
            + "\n\n*(Executed locally while internet connection was unavailable)*"
        )
        return {
            "reply": reply,
            "tool_calls": executed_tools,
            "requires_confirmation": False,
            "affected_path": targets[0] if targets else None,
        }

    # Case C: Create File
    elif action == "create_file":
        file_path = intent.get("file_path", "file.txt")
        content = intent.get("content", "")
        args = {"file_path": file_path, "content": content}
        res_str, diff_data = await _execute_tool_with_diff("create_file", args)
        tool_entry = {
            "name": "create_file",
            "arguments": args,
            "status": "success" if not str(res_str).startswith("Error") else "error",
            "result": res_str,
        }
        if diff_data:
            tool_entry["diff"] = diff_data
        executed_tools.append(tool_entry)

        return {
            "reply": (
                f"⚡ **Offline Execution Active**\n\n"
                f"Successfully created file **`{file_path}`** locally:\n{res_str}\n\n"
                f"*(Executed locally while internet connection was unavailable)*"
            ),
            "tool_calls": executed_tools,
            "requires_confirmation": False,
            "affected_path": file_path,
        }

    # Case D: Read File
    elif action == "read_file":
        file_path = intent.get("file_path", "")
        args = {"file_path": file_path}
        res_str, _ = await _execute_tool_with_diff("read_file", args)
        tool_entry = {
            "name": "read_file",
            "arguments": args,
            "status": "success" if not str(res_str).startswith("Error") else "error",
            "result": res_str,
        }
        executed_tools.append(tool_entry)

        if str(res_str).startswith("Error"):
            reply = f"❌ {res_str}"
        else:
            reply = (
                f"⚡ **Offline Execution Active**\n\n"
                f"**Content of `{file_path}`**:\n```text\n{res_str}\n```"
            )
        return {
            "reply": reply,
            "tool_calls": executed_tools,
            "requires_confirmation": False,
            "affected_path": file_path,
        }

    # Case E: List Folder
    elif action == "list_folder":
        folder_path = intent.get("folder_path", "")
        args = {"folder_path": folder_path}
        res_str, _ = await _execute_tool_with_diff("list_folder", args)
        tool_entry = {
            "name": "list_folder",
            "arguments": args,
            "status": "success" if not str(res_str).startswith("Error") else "error",
            "result": res_str,
        }
        executed_tools.append(tool_entry)

        display_name = folder_path if folder_path else "workspace root"
        return {
            "reply": (
                f"⚡ **Offline Execution Active**\n\n"
                f"**Contents of `{display_name}`**:\n```text\n{res_str}\n```"
            ),
            "tool_calls": executed_tools,
            "requires_confirmation": False,
        }

    # Case F: Update File
    elif action == "update_file":
        file_path = intent.get("file_path", "")
        content = intent.get("content", "")
        mode = intent.get("mode", "overwrite")
        args = {"file_path": file_path, "content": content, "mode": mode}
        res_str, diff_data = await _execute_tool_with_diff("update_file", args)
        tool_entry = {
            "name": "update_file",
            "arguments": args,
            "status": "success" if not str(res_str).startswith("Error") else "error",
            "result": res_str,
        }
        if diff_data:
            tool_entry["diff"] = diff_data
        executed_tools.append(tool_entry)

        return {
            "reply": (
                f"⚡ **Offline Execution Active**\n\n"
                f"Successfully updated **`{file_path}`** locally ({mode} mode):\n{res_str}"
            ),
            "tool_calls": executed_tools,
            "requires_confirmation": False,
            "affected_path": file_path,
        }

    # Case G: Delete Item(s) - ENFORCE CONFIRMATION GATE
    elif action == "delete_item":
        targets = intent.get("targets", [])
        is_everything = intent.get("is_everything", False)

        delete_items = []
        targets_list = []
        for t in targets:
            t_clean = t.strip()
            if is_everything or t_clean.lower() in ("everything", "all", "workspace", "workshop", "*"):
                target_display = "everything in workspace"
                tool_input = {"path": "everything", "recursive": True}
            else:
                target_display = t_clean
                tool_input = {"path": t_clean, "recursive": True}
            targets_list.append(target_display)
            delete_items.append({
                "tool": "delete_item",
                "arguments": tool_input,
                "display": target_display,
            })
            executed_tools.append({
                "name": "delete_item",
                "arguments": tool_input,
                "status": "pending_confirmation",
                "result": f"Awaiting user confirmation before deleting '{target_display}'...",
            })

        conf_id = f"conf_{uuid.uuid4().hex[:8]}"
        display_str = ", ".join(targets_list)
        if len(targets_list) == 1:
            reply_prompt = (
                f"⚠️ **Delete Confirmation Required (Offline Mode)**:\n"
                f"Are you sure you want to permanently delete **`{targets_list[0]}`**? This action cannot be undone."
            )
            details_text = f"Delete '{targets_list[0]}'"
        else:
            formatted_targets = ", ".join(f"`{t}`" for t in targets_list)
            reply_prompt = (
                f"⚠️ **Delete Confirmation Required (Offline Mode)**:\n"
                f"Are you sure you want to permanently delete these {len(targets_list)} items: {formatted_targets}? This action cannot be undone."
            )
            details_text = f"Delete {len(targets_list)} items: {display_str}"

        pending_confirmations[conf_id] = {
            "tool": "batch_delete" if len(delete_items) > 1 else "delete_item",
            "items": delete_items,
            "display_target": display_str,
            "prompt": user_message,
        }

        return {
            "reply": reply_prompt,
            "requires_confirmation": True,
            "confirmation": {
                "id": conf_id,
                "action": "delete_item",
                "target": display_str,
                "details": details_text,
            },
            "tool_calls": executed_tools,
        }

    return {
        "reply": "⚠️ Unrecognized offline command.",
        "tool_calls": [],
        "requires_confirmation": False,
    }
