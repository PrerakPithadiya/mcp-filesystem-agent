"""
LLM Agent Module
Integrates with Claude API (Anthropic) and Google Gemini with MCP tool calling and human-in-the-loop confirmation.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

import anthropic
try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None  # type: ignore
    types = None  # type: ignore

from backend import config
from backend.diff_utils import compute_file_diff
from backend.mcp_client import mcp_client_service
from backend.offline_handler import handle_offline_request, is_network_error, parse_offline_intent
from server.sandbox import get_safe_path

logger = logging.getLogger("llm_agent")

SYSTEM_PROMPT = """You are an intelligent, highly reliable Filesystem Assistant powered by the Model Context Protocol (MCP).
You help users manage their files and folders within a safe workspace.

Key Instructions:
1. Available Tools:
   - `create_folder(folder_path)`: Create a directory (and any necessary parent directories).
   - `create_file(file_path, content)`: Create a new file with text content.
   - `read_file(file_path)`: Read text content of an existing file.
   - `list_folder(folder_path)`: List files and subfolders. Use "" or "." for workspace root.
   - `update_file(file_path, content, mode)`: Overwrite or append to an existing file. Mode is 'overwrite' or 'append'.
   - `delete_item(path, recursive)`: Permanently delete a file or directory. For non-empty folders, set recursive=True.

2. RESPONSE FORMATTING (CRITICAL):
   - Provide CLEAN, CONVERSATIONAL responses only.
   - NEVER include tool call syntax, function names, or technical details in your conversational response.
   - Do NOT write things like "read_file(file_path='config.json')" or "I called the create_folder tool".
   - Instead, write natural responses like "I've read the config file" or "The folder has been created successfully".
   - The tool calls are handled automatically by the system and displayed separately in the UI.
   - Focus on what happened and the result, not the technical implementation.

3. Terse & Minimal Input Handling:
   - Understand short-hand notations accurately:
     * `filename.ext: some text` or `filename: some text` -> User wants to create or update that file with `some text`.
     * `todo: buy milk` -> Create or append to `todo.txt` with "buy milk".
     * `list`, `ls`, `dir`, `files` -> Call `list_folder("")` to list the workspace.
     * `read filename` or `cat filename` -> Call `read_file(filename)`.
     * `rm filename` or `delete filename` -> Call `delete_item(filename)`.
   - Never refuse a task just because the user wrote very little, as long as the intent is reasonably clear.

4. Ambiguity & Vague Input Protection (CRITICAL):
   - If the user gives a vague or underspecified command (such as simply "delete", "remove it", "read", "update") WITHOUT specifying which file/folder AND there is no clear target in recent conversation history:
     * DO NOT guess or pick a random file or folder!
     * DO NOT execute any random or destructive tools!
     * Ask the user politely which file or folder they would like to operate on.

5. Conversational Context & Pronoun Resolution:
   - When the user refers to "it", "that file", "the previous folder", or uses follow-up phrases (e.g. "now change it to...", "read it", "delete it"), resolve the reference from the conversation history.

6. Multi-Item and List Interpretation (CRITICAL INTELLIGENCE RULE):
   - When a user provides a list of names separated by commas, 'and', or conjunctions (e.g. "Create a folder named 'Prerak, Utsav, Umang'", "make folders for Alice, Bob and Charlie", "create directories a, b, c"):
     * ALWAYS interpret this as a request to create MULTIPLE SEPARATE FOLDERS, one for each individual name!
     * NEVER create a single folder or file containing commas in its name like 'Prerak, Utsav, Umang'. Such names are user shorthand for multiple directories.
     * Call `create_folder` separately for each individual name:
       - `create_folder(folder_path="Prerak")`
       - `create_folder(folder_path="Utsav")`
       - `create_folder(folder_path="Umang")`
   - If the user asks to add files inside (e.g. "inside this folder, you need to add three text files" or "inside each folder, add a file"):
     * Create the corresponding file inside each of the created folders:
       - `create_file(file_path="Prerak/prerak.txt", content="...")`
       - `create_file(file_path="Utsav/utsav.txt", content="...")`
       - `create_file(file_path="Umang/umang.txt", content="...")`

7. Deletion & Workspace Wipes (CRITICAL):
   - When the user asks to delete multiple files or folders (e.g. "delete the folder named prerak, umang and utsav", "delete folders a, b, and c", "remove file1.txt and file2.txt"):
     * Call `delete_item` separately for EACH item requested:
       - `delete_item(path="prerak", recursive=True)`
       - `delete_item(path="umang", recursive=True)`
       - `delete_item(path="utsav", recursive=True)`
   - When the user asks to delete anything, such as "delete notes.txt", "delete folder1", or "Delete everything currently in my workshop/workspace", "clear workspace", "wipe all":
     * YOU MUST ALWAYS CALL `delete_item`!
     * NEVER write plain text asking "Are you sure?" yourself! The backend system has an automatic interception gate that catches `delete_item` and presents an interactive UI card with [Confirm Delete] and [Cancel] buttons.
     * If you only write confirmation text without calling `delete_item`, the confirmation buttons will NOT render and the action cannot happen!
     * To delete everything or clear the workspace: call `delete_item(path="everything", recursive=True)`.
     * To delete a specific file or folder: call `delete_item(path=target, recursive=True)`.

8. Security & Sandbox Boundary:
   - All filesystem operations are strictly confined within the safe workspace sandbox.
   - When the user refers to "desktop", "my desktop", or "workspace" (e.g. 'on my desktop', 'from my desktop', 'in my workspace'), treat this as referring directly to the root of the safe workspace. Call the relevant tool with the relative path (e.g. `read_file("report.txt")` or `create_file("report.txt")`), do NOT refuse the request thinking it is outside the sandbox.
   - When a user asks to access, read, write, or delete parent directory references like '..', '../', or outside system files (e.g. 'delete ..', 'rm ..', 'read ../../PRD.md', 'list C:\\Windows'):
     * Treat '..' specifically as the parent directory path, NOT as trailing ellipsis or punctuation.
     * Do NOT treat 'delete ..' as an incomplete sentence.
     * Call the appropriate tool (e.g. `delete_item(path="..")`), which will be intercepted safely by the sandbox with a security violation, or inform the user that accessing or deleting files outside the safe workspace is prohibited.

9. Workspace and Desktop Context:
   - The safe workspace sandbox can be configured directly to the user's Desktop or dedicated workspace directory.
   - When the user refers to "my desktop", "on desktop", "from my desktop", "workspace", or "here":
     * Treat this as referring directly to the workspace root!
     * NEVER refuse by claiming you cannot access their desktop — their workspace IS configured to their desktop!
     * Execute the tool directly using the filename or folder name (e.g. `create_file(file_path="notes.txt")`).
"""

# In-memory store for pending confirmations: {conf_id: {"tool": str, "arguments": dict, "prompt": str}}
PENDING_CONFIRMATIONS: Dict[str, Dict[str, Any]] = {}


async def _execute_tool_with_diff(tool_name: str, tool_input: Dict[str, Any]) -> Tuple[str, Optional[Dict[str, Any]]]:
    """
    Executes an MCP tool and, for file update/create mutations, computes
    a line-by-line structured diff between pre- and post-mutation state.
    """
    old_content = ""
    target_path = tool_input.get("file_path") or tool_input.get("path")
    if tool_name in ("update_file", "create_file") and target_path:
        try:
            safe_p = get_safe_path(target_path)
            if safe_p.exists() and safe_p.is_file():
                old_content = safe_p.read_text(encoding="utf-8")
        except Exception:
            pass

    result_str = await mcp_client_service.call_tool(tool_name, tool_input)

    diff_data = None
    if tool_name in ("update_file", "create_file") and target_path and not str(result_str).startswith("Error"):
        try:
            safe_p = get_safe_path(target_path)
            if safe_p.exists() and safe_p.is_file():
                new_content = safe_p.read_text(encoding="utf-8")
                diff_data = compute_file_diff(old_content, new_content, str(target_path))
        except Exception as ex:
            logger.warning(f"Failed to compute diff for {target_path}: {ex}")

    return str(result_str), diff_data


class LLMAgent:
    def __init__(self):
        self.provider = config.LLM_PROVIDER
        self.anthropic_client: Optional[anthropic.AsyncAnthropic] = None
        if config.ANTHROPIC_API_KEY:
            self.anthropic_client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

    async def _send_gemini_message_with_retry(self, chat_obj: Any, msg_payload: Any, max_retries: int = 2) -> Any:
        """Sends a message to Gemini chat with fast failover and single quick retry for rate limits."""
        for attempt in range(max_retries):
            try:
                return chat_obj.send_message(msg_payload)
            except Exception as ex:
                err_text = str(ex)
                # Auth and key suspension errors must fail immediately with zero retries
                if any(k in err_text for k in ("CONSUMER_SUSPENDED", "API_KEY_INVALID", "PERMISSION_DENIED", "403")):
                    raise ex
                if ("429" in err_text or "RESOURCE_EXHAUSTED" in err_text or "503" in err_text) and attempt < max_retries - 1:
                    logger.warning(f"Gemini API rate limit/busy ({err_text[:70]}...). Quick retry in 0.3s (attempt {attempt+1}/{max_retries})...")
                    await asyncio.sleep(0.3)
                    continue
                elif is_network_error(ex) and attempt < 1:
                    logger.warning(f"Transient network/DNS drop ({err_text[:70]}...). Retrying in 0.3s...")
                    await asyncio.sleep(0.3)
                    continue
                raise ex

    async def chat(self, user_message: str, history: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Main chat entrypoint. Routes user message through the selected LLM provider.
        """
        # Check if this is a direct response to a pending confirmation
        user_lower = user_message.strip().lower()
        if PENDING_CONFIRMATIONS and user_lower in ("yes", "y", "confirm", "proceed", "sure", "do it"):
            # Execute the latest pending confirmation
            last_id = list(PENDING_CONFIRMATIONS.keys())[-1]
            return await self.resolve_confirmation(last_id, confirmed=True)
        elif PENDING_CONFIRMATIONS and user_lower in ("no", "n", "cancel", "stop", "abort"):
            last_id = list(PENDING_CONFIRMATIONS.keys())[-1]
            return await self.resolve_confirmation(last_id, confirmed=False)

        # Retrieve available MCP tools
        mcp_tools = await mcp_client_service.list_tools()

        if self.provider == "gemini" and config.GEMINI_API_KEY:
            return await self._chat_gemini(user_message, history, mcp_tools)
        elif config.GEMINI_API_KEY:
            return await self._chat_gemini(user_message, history, mcp_tools)
        elif self.provider == "anthropic" and self.anthropic_client:
            return await self._chat_anthropic(user_message, history, mcp_tools)
        elif self.anthropic_client:
            return await self._chat_anthropic(user_message, history, mcp_tools)
        else:
            return {
                "reply": "⚠️ No LLM API key configured! Please provide your `GEMINI_API_KEY` in the `.env` file to enable the Gemini AI brain.",
                "tool_calls": [],
                "requires_confirmation": False,
            }

    async def _chat_anthropic(
        self, user_message: str, history: List[Dict[str, str]], mcp_tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Handles chat with Claude 3.5 via Anthropic SDK with tool calling loop."""
        tools_param = [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["input_schema"],
            }
            for t in mcp_tools
        ]

        # Build messages list
        messages: List[Dict[str, Any]] = []
        for msg in history:
            role = "assistant" if msg.get("role") == "assistant" else "user"
            messages.append({"role": role, "content": msg.get("content", "")})

        messages.append({"role": "user", "content": user_message})

        executed_tools: List[Dict[str, Any]] = []

        try:
            # First turn: Ask Claude
            response = await self.anthropic_client.messages.create(
                model=config.CLAUDE_MODEL,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=tools_param,
                max_tokens=2048,
            )

            # Check if Claude requested tool calls
            tool_use_blocks = [b for b in response.content if b.type == "tool_use"]
            text_blocks = [b for b in response.content if b.type == "text"]

            if not tool_use_blocks:
                reply_text = "".join(b.text for b in text_blocks) if text_blocks else "Done."
                return {
                    "reply": reply_text,
                    "tool_calls": [],
                    "requires_confirmation": False,
                }

            # Process tools
            tool_results_content = []
            requires_conf = False
            conf_details = None

            # Separate destructive delete calls from non-destructive calls
            delete_blocks = [b for b in tool_use_blocks if b.name == "delete_item"]
            other_blocks = [b for b in tool_use_blocks if b.name != "delete_item"]

            if delete_blocks:
                delete_items = []
                targets_list = []
                for tool_call in delete_blocks:
                    tool_input = tool_call.input or {}
                    target_path = str(tool_input.get("path", "unknown")).strip()
                    is_everything = target_path.lower() in ("everything", "*", "all", "all items", "workspace", "workshop", ".")
                    if is_everything:
                        target_display = "everything in workspace"
                        tool_input["recursive"] = True
                        tool_input["path"] = "everything"
                    else:
                        target_display = target_path
                        try:
                            from server.sandbox import get_safe_path
                            safe_p = get_safe_path(target_path)
                            if safe_p.is_dir() and not tool_input.get("recursive"):
                                tool_input["recursive"] = True
                        except Exception:
                            pass
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
                if len(targets_list) == 1:
                    single_target = targets_list[0]
                    reply_prompt = f"⚠️ **Delete Confirmation Required**:\nAre you sure you want to permanently delete **`{single_target}`**? This action cannot be undone."
                    details_text = f"Delete '{single_target}'"
                else:
                    formatted_targets = ", ".join(f"`{t}`" for t in targets_list)
                    reply_prompt = f"⚠️ **Delete Confirmation Required**:\nAre you sure you want to permanently delete these {len(targets_list)} items: {formatted_targets}? This action cannot be undone."
                    details_text = f"Delete {len(targets_list)} items: {', '.join(targets_list)}"

                PENDING_CONFIRMATIONS[conf_id] = {
                    "tool": "batch_delete" if len(delete_items) > 1 else "delete_item",
                    "items": delete_items,
                    "display_target": ", ".join(targets_list),
                    "prompt": user_message,
                }

                return {
                    "reply": reply_prompt,
                    "requires_confirmation": True,
                    "confirmation": {
                        "id": conf_id,
                        "action": "delete_item",
                        "target": ", ".join(targets_list),
                        "details": details_text,
                    },
                    "tool_calls": executed_tools,
                }

            # Non-destructive tools: Execute immediately
            for tool_call in other_blocks:
                tool_name = tool_call.name
                tool_input = tool_call.input
                result_str, diff_data = await _execute_tool_with_diff(tool_name, tool_input)
                tool_record = {
                    "name": tool_name,
                    "arguments": tool_input,
                    "status": "success" if not result_str.startswith("Error") else "error",
                    "result": result_str,
                }
                if diff_data:
                    tool_record["diff"] = diff_data
                executed_tools.append(tool_record)
                tool_results_content.append({
                    "type": "tool_result",
                    "tool_use_id": tool_call.id,
                    "content": result_str,
                })

            # Send tool results back to Claude for final response synthesis
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results_content})

            second_response = await self.anthropic_client.messages.create(
                model=config.CLAUDE_MODEL,
                system=SYSTEM_PROMPT,
                messages=messages,
                tools=tools_param,
                max_tokens=2048,
            )

            final_text_blocks = [b for b in second_response.content if b.type == "text"]
            final_reply = "".join(b.text for b in final_text_blocks) if final_text_blocks else "Operation completed."

            return {
                "reply": final_reply,
                "tool_calls": executed_tools,
                "requires_confirmation": False,
            }

        except Exception as e:
            logger.error(f"Anthropic API error: {e}", exc_info=True)
            return {
                "reply": f"❌ Error communicating with Claude API: {str(e)}",
                "tool_calls": executed_tools,
                "requires_confirmation": False,
            }

    async def _chat_gemini(
        self, user_message: str, history: List[Dict[str, str]], mcp_tools: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Primary chat using Google Gemini with MCP tool calling and confirmation."""
        try:
            client = genai.Client(api_key=config.GEMINI_API_KEY)

            # Convert tools to Gemini function declarations
            function_declarations = []
            for t in mcp_tools:
                decl = types.FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters=t.get("input_schema", {}),
                )
                function_declarations.append(decl)

            gemini_tools = [types.Tool(function_declarations=function_declarations)]

            # Convert history to Gemini Content objects (optimized to last 4 messages for speed)
            chat_history: List[types.Content] = []
            for h in history[-4:]:
                role = "model" if h.get("role") == "assistant" else "user"
                content_text = (h.get("content") or "").strip()
                if content_text:
                    chat_history.append(
                        types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=content_text)],
                        )
                    )

            # Fast responsive models first
            primary_model = config.GEMINI_MODEL
            fallback_models = ["gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-2.5-flash", "gemini-3.5-flash-lite"]
            models_to_try = [primary_model] + [m for m in fallback_models if m != primary_model]
            last_err = None

            for model_name in models_to_try:
                try:
                    chat = client.chats.create(
                        model=model_name,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_PROMPT,
                            tools=gemini_tools,
                        ),
                        history=chat_history if chat_history else None,
                    )
                    response = await self._send_gemini_message_with_retry(chat, user_message)
                    break
                except Exception as e:
                    err_str = str(e)
                    if is_network_error(e):
                        logger.warning(f"Model {model_name} network error: {err_str[:80]}... Activating offline fallback.")
                        last_err = e
                        break
                    if any(k in err_str for k in ("CONSUMER_SUSPENDED", "API_KEY_INVALID", "PERMISSION_DENIED", "403")):
                        logger.warning(f"Model {model_name} authentication/suspension error: {err_str[:80]}... Aborting model loop.")
                        last_err = e
                        break
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str or "404" in err_str:
                        logger.warning(f"Model {model_name} failed ({err_str[:80]}...); trying fallback.")
                        last_err = e
                        continue
                    raise e
            else:
                if last_err:
                    raise last_err

            if last_err and is_network_error(last_err):
                raise last_err
            executed_tools: List[Dict[str, Any]] = []

            # Tool calling loop (up to 5 rounds)
            max_rounds = 5
            round_count = 0

            while response.function_calls and round_count < max_rounds:
                round_count += 1
                function_responses = []

                # Separate destructive delete calls from non-destructive calls
                delete_fcs = [fc for fc in response.function_calls if fc.name == "delete_item"]
                other_fcs = [fc for fc in response.function_calls if fc.name != "delete_item"]

                # If there are delete calls, batch ALL of them into a single confirmation
                if delete_fcs:
                    delete_items = []
                    targets_list = []
                    for fc in delete_fcs:
                        tool_input = dict(fc.args) if fc.args else {}
                        target_path = str(tool_input.get("path", "unknown")).strip()
                        is_everything = target_path.lower() in ("everything", "*", "all", "all items", "workspace", "workshop", ".")
                        if is_everything:
                            target_display = "everything in workspace"
                            tool_input["recursive"] = True
                            tool_input["path"] = "everything"
                        else:
                            target_display = target_path
                            try:
                                from server.sandbox import get_safe_path
                                safe_p = get_safe_path(target_path)
                                if safe_p.is_dir() and not tool_input.get("recursive"):
                                    tool_input["recursive"] = True
                            except PermissionError as pe:
                                return {
                                    "reply": f"🛡️ **Security Boundary Violation**: Cannot delete `{target_path}`. Operations attempting to access or delete files outside the safe workspace are strictly prohibited.",
                                    "tool_calls": [{
                                        "name": "delete_item",
                                        "arguments": tool_input,
                                        "status": "error",
                                        "result": str(pe),
                                    }],
                                    "requires_confirmation": False,
                                }
                            except Exception:
                                pass
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
                    if len(targets_list) == 1:
                        single_target = targets_list[0]
                        reply_prompt = f"⚠️ **Delete Confirmation Required**:\nAre you sure you want to permanently delete **`{single_target}`**? This action cannot be undone."
                        details_text = f"Delete '{single_target}'"
                    else:
                        formatted_targets = ", ".join(f"`{t}`" for t in targets_list)
                        reply_prompt = f"⚠️ **Delete Confirmation Required**:\nAre you sure you want to permanently delete these {len(targets_list)} items: {formatted_targets}? This action cannot be undone."
                        details_text = f"Delete {len(targets_list)} items: {', '.join(targets_list)}"

                    PENDING_CONFIRMATIONS[conf_id] = {
                        "tool": "batch_delete" if len(delete_items) > 1 else "delete_item",
                        "items": delete_items,
                        "display_target": ", ".join(targets_list),
                        "prompt": user_message,
                    }

                    return {
                        "reply": reply_prompt,
                        "requires_confirmation": True,
                        "confirmation": {
                            "id": conf_id,
                            "action": "delete_item",
                            "target": ", ".join(targets_list),
                            "details": details_text,
                        },
                        "tool_calls": executed_tools,
                    }

                # Non-destructive tools: Execute immediately
                for fc in other_fcs:
                    tool_name = fc.name
                    tool_input = dict(fc.args) if fc.args else {}
                    result_str, diff_data = await _execute_tool_with_diff(tool_name, tool_input)
                    tool_entry = {
                        "name": tool_name,
                        "arguments": tool_input,
                        "status": "success" if not str(result_str).startswith("Error") else "error",
                        "result": result_str,
                    }
                    if diff_data:
                        tool_entry["diff"] = diff_data
                    executed_tools.append(tool_entry)

                    function_responses.append(
                        types.Part.from_function_response(
                            name=tool_name,
                            response={"result": result_str},
                        )
                    )

                # Send function results back to Gemini for next step or synthesis
                if function_responses:
                    response = await self._send_gemini_message_with_retry(chat, function_responses)
                else:
                    break

            try:
                reply_text = response.text or "Operation completed successfully."
            except (ValueError, AttributeError):
                reply_text = "Operation completed successfully."

            # Safety Net 1: Intercept path traversal deletion attempts (e.g. 'delete ..', 'rm ..', 'delete ../../README.md')
            user_msg_lower = user_message.strip().lower()
            is_delete_req = any(k in user_msg_lower for k in ["delete", "remove", "wipe", "clear", "erase", "destroy", "rm"])
            user_words = [w.strip("',\"") for w in user_msg_lower.split()]
            is_traversal_delete = any(w in ("..", "../", "../../") for w in user_words) or any(t in user_msg_lower for t in ["/etc/", "c:\\", "c:/", "../"])
            if is_delete_req and is_traversal_delete:
                return {
                    "reply": "🛡️ **Security Boundary Violation**: Deleting files or directories outside the safe workspace sandbox (such as `..`) is strictly prohibited.",
                    "tool_calls": [],
                    "requires_confirmation": False,
                }

            # Safety Net 2: If the user requested to delete everything / all items / wipe workspace,
            # but the model only listed items or outputted text asking for confirmation without invoking delete_item:
            is_everything_req = any(k in user_msg_lower for k in ["everything", "all", "workspace", "workshop", "all files", "all folders"])
            has_delete_tool = any(t.get("name") == "delete_item" for t in executed_tools)

            if is_delete_req and not has_delete_tool and (is_everything_req or "confirm" in reply_text.lower() or "sure" in reply_text.lower()):
                target_path = "everything" if is_everything_req else "item"
                target_display = "everything in workspace" if is_everything_req else target_path
                conf_id = f"conf_{uuid.uuid4().hex[:8]}"
                PENDING_CONFIRMATIONS[conf_id] = {
                    "tool": "delete_item",
                    "arguments": {"path": target_path, "recursive": True},
                    "prompt": user_message,
                }
                executed_tools.append({
                    "name": "delete_item",
                    "arguments": {"path": target_path, "recursive": True},
                    "status": "pending_confirmation",
                    "result": "Awaiting user confirmation before deleting...",
                })
                return {
                    "reply": f"⚠️ **Delete Confirmation Required**:\nAre you sure you want to permanently delete **`{target_display}`**? This action cannot be undone.",
                    "requires_confirmation": True,
                    "confirmation": {
                        "id": conf_id,
                        "action": "delete_item",
                        "target": target_display,
                        "details": f"Delete '{target_display}' (and all contents)",
                    },
                    "tool_calls": executed_tools,
                }

            return {
                "reply": reply_text,
                "tool_calls": executed_tools,
                "requires_confirmation": False,
            }

        except Exception as e:
            err_str = str(e)
            intent = parse_offline_intent(user_message, history)
            if is_network_error(e) or (intent and any(k in err_str for k in ("CONSUMER_SUSPENDED", "429", "RESOURCE_EXHAUSTED"))):
                logger.warning(f"Gemini API exception ({err_str[:80]}). Executing high-speed offline fallback.")
                res = await handle_offline_request(intent, user_message, PENDING_CONFIRMATIONS)
                if "CONSUMER_SUSPENDED" in err_str and res.get("reply"):
                    res["reply"] += "\n\n*(Note: Executed locally in 10ms. Google API key is suspended (403); update .env for full cloud AI reasoning.)*"
                return res

            logger.error(f"Gemini API error: {e}", exc_info=True)
            if "CONSUMER_SUSPENDED" in err_str:
                return {
                    "reply": (
                        "❌ **Google Gemini API Key Suspended (403)**\n\n"
                        "Google has suspended the project associated with this API key.\n\n"
                        "**To fix this:**\n"
                        "1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)\n"
                        "2. Click **Create API key** and select **Create API key in NEW project**\n"
                        "3. Paste the key into `.env` as `GEMINI_API_KEY=...`\n"
                        "4. Send a new message — it will be loaded automatically!"
                    ),
                    "tool_calls": [],
                    "requires_confirmation": False,
                }
            elif "API_KEY_INVALID" in err_str or "API key not valid" in err_str or "PERMISSION_DENIED" in err_str:
                return {
                    "reply": (
                        "❌ **Invalid Google Gemini API Key**\n\n"
                        "The Gemini API key in your `.env` file is invalid or unauthorized.\n\n"
                        "**To fix this:**\n"
                        "1. Go to [Google AI Studio](https://aistudio.google.com/app/apikey)\n"
                        "2. Copy a valid API key\n"
                        "3. Update `.env` with `GEMINI_API_KEY=your_key_here`\n"
                        "4. Send a new message — it will reload automatically!"
                    ),
                    "tool_calls": [],
                    "requires_confirmation": False,
                }
            elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                return {
                    "reply": (
                        "⚠️ **Gemini Free Tier Quota Exceeded (429)**\n\n"
                        "The rate limit for free tier requests was reached. "
                        "Please wait a few seconds and send your request again! "
                        "The app automatically uses `gemini-3.5-flash-lite` which has the highest available free quota."
                    ),
                    "tool_calls": [],
                    "requires_confirmation": False,
                }
            return {
                "reply": f"❌ Error communicating with Google Gemini API: {str(e)}",
                "tool_calls": [],
                "requires_confirmation": False,
            }

    async def resolve_confirmation(self, conf_id: str, confirmed: bool) -> Dict[str, Any]:
        """Resolves a pending delete action after the user clicks Confirm or Cancel."""
        action_data = PENDING_CONFIRMATIONS.pop(conf_id, None)
        if not action_data:
            return {
                "reply": "⚠️ Confirmation request expired or already processed.",
                "tool_calls": [],
                "requires_confirmation": False,
            }

        items = action_data.get("items")
        if not items:
            items = [{"tool": action_data.get("tool", "delete_item"), "arguments": action_data.get("arguments", {})}]

        target = action_data.get("display_target") or action_data.get("arguments", {}).get("path", "item")

        if not confirmed:
            return {
                "reply": f"🛑 Deletion cancelled. **`{target}`** was not deleted.",
                "tool_calls": [{
                    "name": item["tool"],
                    "arguments": item["arguments"],
                    "status": "cancelled",
                    "result": "User cancelled deletion.",
                } for item in items],
                "requires_confirmation": False,
            }

        # User confirmed -> execute all items via MCP
        executed_tools = []
        result_messages = []
        for item in items:
            res_str = await mcp_client_service.call_tool(item["tool"], item["arguments"])
            status = "success" if not res_str.startswith("Error") else "error"
            executed_tools.append({
                "name": item["tool"],
                "arguments": item["arguments"],
                "status": status,
                "result": res_str,
            })
            result_messages.append(res_str)

        if len(items) == 1:
            reply_text = f"🗑️ Confirmed: {result_messages[0]}"
        else:
            reply_text = f"🗑️ Confirmed: Successfully processed {len(items)} deletions:\n" + "\n".join(f"- {msg}" for msg in result_messages)

        return {
            "reply": reply_text,
            "tool_calls": executed_tools,
            "requires_confirmation": False,
        }

    async def chat_stream(self, user_message: str, history: List[Dict[str, str]]):
        """
        Streams agent lifecycle and text response via Server-Sent Events (SSE).
        Yields strings formatted as:
            event: <type>\n
            data: <json>\n\n
        """
        user_lower = user_message.strip().lower()
        if PENDING_CONFIRMATIONS and user_lower in ("yes", "y", "confirm", "proceed", "sure", "do it"):
            last_id = list(PENDING_CONFIRMATIONS.keys())[-1]
            res = await self.resolve_confirmation(last_id, confirmed=True)
            yield f"event: done\ndata: {json.dumps(res)}\n\n"
            return
        elif PENDING_CONFIRMATIONS and user_lower in ("no", "n", "cancel", "stop", "abort"):
            last_id = list(PENDING_CONFIRMATIONS.keys())[-1]
            res = await self.resolve_confirmation(last_id, confirmed=False)
            yield f"event: done\ndata: {json.dumps(res)}\n\n"
            return

        if not config.GEMINI_API_KEY and not config.ANTHROPIC_API_KEY:
            err_msg = "⚠️ No LLM API key configured! Please provide your `GEMINI_API_KEY` in the `.env` file."
            yield f"event: error\ndata: {json.dumps({'error': err_msg})}\n\n"
            return

        yield f"event: status\ndata: {json.dumps({'stage': 'thinking', 'message': 'Analyzing request...'})}\n\n"

        mcp_tools = await mcp_client_service.list_tools()

        if self.provider == "gemini" and config.GEMINI_API_KEY:
            async for chunk in self._chat_gemini_stream(user_message, history, mcp_tools):
                yield chunk
        elif config.GEMINI_API_KEY:
            async for chunk in self._chat_gemini_stream(user_message, history, mcp_tools):
                yield chunk
        else:
            # Fallback to non-streaming for alternative providers
            res = await self.chat(user_message, history)
            for tc in res.get("tool_calls", []):
                yield f"event: tool_end\ndata: {json.dumps(tc)}\n\n"
            if res.get("requires_confirmation"):
                yield f"event: confirmation_required\ndata: {json.dumps(res)}\n\n"
                return
            reply = res.get("reply", "")
            yield f"event: status\ndata: {json.dumps({'stage': 'generating', 'message': 'Generating response...'})}\n\n"
            words = reply.split(" ")
            for i, w in enumerate(words):
                chunk_str = w + (" " if i < len(words) - 1 else "")
                yield f"event: token\ndata: {json.dumps({'delta': chunk_str})}\n\n"
            yield f"event: done\ndata: {json.dumps(res)}\n\n"

    async def _chat_gemini_stream(
        self, user_message: str, history: List[Dict[str, str]], mcp_tools: List[Dict[str, Any]]
    ):
        """Streaming handler for Google Gemini via SSE."""
        try:
            client = genai.Client(api_key=config.GEMINI_API_KEY)

            # Convert tools to Gemini function declarations
            function_declarations = []
            for t in mcp_tools:
                decl = types.FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters=t.get("input_schema", {}),
                )
                function_declarations.append(decl)

            gemini_tools = [types.Tool(function_declarations=function_declarations)]

            chat_history: List[types.Content] = []
            for h in history[-4:]:
                role = "model" if h.get("role") == "assistant" else "user"
                content_text = (h.get("content") or "").strip()
                if content_text:
                    chat_history.append(
                        types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=content_text)],
                        )
                    )

            # Fast responsive models first
            primary_model = config.GEMINI_MODEL
            fallback_models = ["gemini-3.1-flash-lite", "gemini-3.6-flash", "gemini-2.5-flash", "gemini-3.5-flash-lite"]
            models_to_try = [primary_model] + [m for m in fallback_models if m != primary_model]
            chat = None
            response = None
            last_err = None

            for model_name in models_to_try:
                try:
                    chat = client.chats.create(
                        model=model_name,
                        config=types.GenerateContentConfig(
                            system_instruction=SYSTEM_PROMPT,
                            tools=gemini_tools,
                        ),
                        history=chat_history if chat_history else None,
                    )
                    response = await self._send_gemini_message_with_retry(chat, user_message)
                    break
                except Exception as e:
                    err_str = str(e)
                    if is_network_error(e):
                        logger.warning(f"Model {model_name} network error in stream: {err_str[:80]}... Activating offline fallback.")
                        last_err = e
                        break
                    if any(k in err_str for k in ("CONSUMER_SUSPENDED", "API_KEY_INVALID", "PERMISSION_DENIED", "403")):
                        logger.warning(f"Model {model_name} auth/suspension error in stream: {err_str[:80]}... Aborting model loop.")
                        last_err = e
                        break
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str or "404" in err_str:
                        logger.warning(f"Model {model_name} failed: {err_str[:80]}... Trying fallback.")
                        last_err = e
                        continue
                    raise e
            else:
                if last_err:
                    if is_network_error(last_err):
                        raise last_err
                    yield f"event: error\ndata: {json.dumps({'error': str(last_err)})}\n\n"
                    return

            if last_err and is_network_error(last_err):
                raise last_err

            executed_tools: List[Dict[str, Any]] = []
            max_rounds = 5
            round_count = 0

            while response.function_calls and round_count < max_rounds:
                round_count += 1
                function_responses = []

                delete_fcs = [fc for fc in response.function_calls if fc.name == "delete_item"]
                other_fcs = [fc for fc in response.function_calls if fc.name != "delete_item"]

                if delete_fcs:
                    delete_items = []
                    targets_list = []
                    for fc in delete_fcs:
                        tool_input = dict(fc.args) if fc.args else {}
                        target_path = str(tool_input.get("path", "unknown")).strip()
                        is_everything = target_path.lower() in ("everything", "*", "all", "all items", "workspace", "workshop", ".")
                        if is_everything:
                            target_display = "everything in workspace"
                            tool_input["recursive"] = True
                            tool_input["path"] = "everything"
                        else:
                            target_display = target_path
                            try:
                                safe_p = get_safe_path(target_path)
                                if safe_p.is_dir() and not tool_input.get("recursive"):
                                    tool_input["recursive"] = True
                            except PermissionError as pe:
                                yield f"event: error\ndata: {json.dumps({'error': f'Security Boundary Violation: Cannot delete `{target_path}`.'})}\n\n"
                                return
                            except Exception:
                                pass
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
                    if len(targets_list) == 1:
                        single_target = targets_list[0]
                        reply_prompt = f"⚠️ **Delete Confirmation Required**:\nAre you sure you want to permanently delete **`{single_target}`**? This action cannot be undone."
                        details_text = f"Delete '{single_target}'"
                    else:
                        formatted_targets = ", ".join(f"`{t}`" for t in targets_list)
                        reply_prompt = f"⚠️ **Delete Confirmation Required**:\nAre you sure you want to permanently delete these {len(targets_list)} items: {formatted_targets}? This action cannot be undone."
                        details_text = f"Delete {len(targets_list)} items: {', '.join(targets_list)}"

                    PENDING_CONFIRMATIONS[conf_id] = {
                        "tool": "batch_delete" if len(delete_items) > 1 else "delete_item",
                        "items": delete_items,
                        "display_target": ", ".join(targets_list),
                        "prompt": user_message,
                    }

                    yield f"event: confirmation_required\ndata: {json.dumps({'reply': reply_prompt, 'requires_confirmation': True, 'confirmation': {'id': conf_id, 'action': 'delete_item', 'target': ', '.join(targets_list), 'details': details_text}, 'tool_calls': executed_tools})}\n\n"
                    return

                # Non-destructive tools
                yield f"event: status\ndata: {json.dumps({'stage': 'calling_tools', 'message': f'Executing {len(other_fcs)} tool action(s)...'})}\n\n"
                for fc in other_fcs:
                    tool_name = fc.name
                    tool_input = dict(fc.args) if fc.args else {}
                    yield f"event: tool_start\ndata: {json.dumps({'name': tool_name, 'arguments': tool_input})}\n\n"
                    result_str, diff_data = await _execute_tool_with_diff(tool_name, tool_input)
                    tool_entry = {
                        "name": tool_name,
                        "arguments": tool_input,
                        "status": "success" if not str(result_str).startswith("Error") else "error",
                        "result": result_str,
                    }
                    if diff_data:
                        tool_entry["diff"] = diff_data
                    executed_tools.append(tool_entry)
                    yield f"event: tool_end\ndata: {json.dumps(tool_entry)}\n\n"
                    function_responses.append(
                        types.Part.from_function_response(
                            name=tool_name,
                            response={"result": result_str},
                        )
                    )

                if function_responses:
                    response = await self._send_gemini_message_with_retry(chat, function_responses)
                else:
                    break

            try:
                reply_text = response.text or "Operation completed successfully."
            except (ValueError, AttributeError):
                reply_text = "Operation completed successfully."

            # Safety Net 1: Intercept path traversal deletion attempts
            user_msg_lower = user_message.strip().lower()
            is_delete_req = any(k in user_msg_lower for k in ["delete", "remove", "wipe", "clear", "erase", "destroy", "rm"])
            user_words = [w.strip("',\"") for w in user_msg_lower.split()]
            is_traversal_delete = any(w in ("..", "../", "../../") for w in user_words) or any(t in user_msg_lower for t in ["/etc/", "c:\\", "c:/", "../"])
            if is_delete_req and is_traversal_delete:
                reply_text = "🛡️ **Security Boundary Violation**: Deleting files or directories outside the safe workspace sandbox (such as `..`) is strictly prohibited."
                yield f"event: done\ndata: {json.dumps({'reply': reply_text, 'tool_calls': [], 'requires_confirmation': False})}\n\n"
                return

            # Safety Net 2: Workspace wipe request without tool execution
            is_everything_req = any(k in user_msg_lower for k in ["everything", "all", "workspace", "workshop", "all files", "all folders"])
            has_delete_tool = any(t.get("name") == "delete_item" for t in executed_tools)
            if is_delete_req and not has_delete_tool and (is_everything_req or "confirm" in reply_text.lower() or "sure" in reply_text.lower()):
                target_path = "everything" if is_everything_req else "item"
                target_display = "everything in workspace" if is_everything_req else target_path
                conf_id = f"conf_{uuid.uuid4().hex[:8]}"
                PENDING_CONFIRMATIONS[conf_id] = {
                    "tool": "delete_item",
                    "arguments": {"path": target_path, "recursive": True},
                    "prompt": user_message,
                }
                executed_tools.append({
                    "name": "delete_item",
                    "arguments": {"path": target_path, "recursive": True},
                    "status": "pending_confirmation",
                    "result": "Awaiting user confirmation before deleting...",
                })
                yield f"event: confirmation_required\ndata: {json.dumps({'reply': f'⚠️ **Delete Confirmation Required**:\nAre you sure you want to permanently delete **`{target_display}`**? This action cannot be undone.', 'requires_confirmation': True, 'confirmation': {'id': conf_id, 'action': 'delete_item', 'target': target_display, 'details': f'Delete {target_display}'}, 'tool_calls': executed_tools})}\n\n"
                return

            # Stream conversational tokens smoothly
            yield f"event: status\ndata: {json.dumps({'stage': 'generating', 'message': 'Generating response...'})}\n\n"
            words = reply_text.split(" ")
            for i, word in enumerate(words):
                token_str = word + (" " if i < len(words) - 1 else "")
                yield f"event: token\ndata: {json.dumps({'delta': token_str})}\n\n"

            # Determine affected path for UI animation
            affected_path = None
            for t in executed_tools:
                args = t.get("arguments", {})
                p = args.get("folder_path") or args.get("file_path") or args.get("path")
                if p and isinstance(p, str):
                    affected_path = p
                    break

            yield f"event: done\ndata: {json.dumps({'reply': reply_text, 'tool_calls': executed_tools, 'affected_path': affected_path, 'requires_confirmation': False})}\n\n"

        except Exception as e:
            err_str = str(e)
            if is_network_error(e) or "CONSUMER_SUSPENDED" in err_str or "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                logger.warning(f"Stream exception ({err_str[:80]}). Executing high-speed offline fallback stream.")
                intent = parse_offline_intent(user_message, history)
                offline_res = await handle_offline_request(intent, user_message, PENDING_CONFIRMATIONS)

                if "CONSUMER_SUSPENDED" in err_str and offline_res.get("reply"):
                    offline_res["reply"] += "\n\n*(Note: Executed locally in 10ms. Google API key is suspended (403); update .env for full cloud AI reasoning.)*"

                if offline_res.get("requires_confirmation"):
                    yield f"event: confirmation_required\ndata: {json.dumps(offline_res)}\n\n"
                    return

                executed_tools = offline_res.get("tool_calls", [])
                if executed_tools:
                    yield f"event: status\ndata: {json.dumps({'stage': 'calling_tools', 'message': f'Executing {len(executed_tools)} local tool(s)...'})}\n\n"
                    for tc in executed_tools:
                        yield f"event: tool_start\ndata: {json.dumps({'name': tc['name'], 'arguments': tc['arguments']})}\n\n"
                        yield f"event: tool_end\ndata: {json.dumps(tc)}\n\n"

                reply_text = offline_res.get("reply", "")
                yield f"event: status\ndata: {json.dumps({'stage': 'generating', 'message': 'Generating response...'})}\n\n"
                words = reply_text.split(" ")
                for i, word in enumerate(words):
                    token_str = word + (" " if i < len(words) - 1 else "")
                    yield f"event: token\ndata: {json.dumps({'delta': token_str})}\n\n"

                yield f"event: done\ndata: {json.dumps(offline_res)}\n\n"
                return

            err_str = str(e)
            logger.error(f"Error in _chat_gemini_stream: {e}", exc_info=True)
            if "CONSUMER_SUSPENDED" in err_str:
                err_msg = "Google Gemini API Key Suspended (403). Please generate a new key at https://aistudio.google.com/app/apikey and update .env."
            elif "API_KEY_INVALID" in err_str or "API key not valid" in err_str or "PERMISSION_DENIED" in err_str:
                err_msg = "Invalid Google Gemini API Key. Please verify your GEMINI_API_KEY in .env."
            elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                err_msg = "Gemini Free Tier Quota Exceeded (429). Please wait a few seconds and try again."
            else:
                err_msg = str(e)
            yield f"event: error\ndata: {json.dumps({'error': err_msg})}\n\n"


llm_agent = LLMAgent()
