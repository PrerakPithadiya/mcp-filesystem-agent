"""
LLM Agent Module
Integrates with Claude API (Anthropic) and Google Gemini with MCP tool calling and human-in-the-loop confirmation.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

import anthropic
from backend import config
from backend.mcp_client import mcp_client_service

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
   - When a user asks to access, read, write, or delete parent directory references like '..', '../', or outside system files (e.g. 'delete ..', 'rm ..', 'read ../../PRD.md', 'list C:\\Windows'):
     * Treat '..' specifically as the parent directory path, NOT as trailing ellipsis or punctuation.
     * Do NOT treat 'delete ..' as an incomplete sentence.
     * Call the appropriate tool (e.g. `delete_item(path="..")`), which will be intercepted safely by the sandbox with a security violation, or inform the user that accessing or deleting files outside the safe workspace is prohibited.
"""

# In-memory store for pending confirmations: {conf_id: {"tool": str, "arguments": dict, "prompt": str}}
PENDING_CONFIRMATIONS: Dict[str, Dict[str, Any]] = {}


class LLMAgent:
    def __init__(self):
        self.provider = config.LLM_PROVIDER
        self.anthropic_client: Optional[anthropic.AsyncAnthropic] = None
        if config.ANTHROPIC_API_KEY:
            self.anthropic_client = anthropic.AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY)

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
                result_str = await mcp_client_service.call_tool(tool_name, tool_input)
                executed_tools.append({
                    "name": tool_name,
                    "arguments": tool_input,
                    "status": "success" if not result_str.startswith("Error") else "error",
                    "result": result_str,
                })
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
            from google import genai
            from google.genai import types

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

            # Convert history to Gemini Content objects
            chat_history: List[types.Content] = []
            for h in history[-8:]:
                role = "model" if h.get("role") == "assistant" else "user"
                content_text = (h.get("content") or "").strip()
                if content_text:
                    chat_history.append(
                        types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=content_text)],
                        )
                    )

            import asyncio

            async def _send_with_retry(chat_obj, msg_payload, max_retries=4):
                for attempt in range(max_retries):
                    try:
                        return chat_obj.send_message(msg_payload)
                    except Exception as ex:
                        err_text = str(ex)
                        if ("429" in err_text or "RESOURCE_EXHAUSTED" in err_text or "503" in err_text) and attempt < max_retries - 1:
                            backoff = 2.5 * (attempt + 1)
                            logger.warning(f"Gemini API rate limit/busy ({err_text[:70]}...). Retrying in {backoff}s (attempt {attempt+1}/{max_retries})...")
                            await asyncio.sleep(backoff)
                            continue
                        raise ex

            candidate_models = [config.GEMINI_MODEL, "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-3.6-flash"]
            models_to_try = list(dict.fromkeys([m for m in candidate_models if m]))
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
                    response = await _send_with_retry(chat, user_message)
                    break
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str or "404" in err_str:
                        logger.warning(f"Model {model_name} failed ({err_str[:80]}...); trying fallback.")
                        last_err = e
                        continue
                    raise e
            else:
                if last_err:
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
                    result_str = await mcp_client_service.call_tool(tool_name, tool_input)
                    executed_tools.append({
                        "name": tool_name,
                        "arguments": tool_input,
                        "status": "success" if not str(result_str).startswith("Error") else "error",
                        "result": result_str,
                    })

                    function_responses.append(
                        types.Part.from_function_response(
                            name=tool_name,
                            response={"result": result_str},
                        )
                    )

                # Send function results back to Gemini for next step or synthesis
                if function_responses:
                    response = await _send_with_retry(chat, function_responses)
                else:
                    break

            reply_text = response.text or "Operation completed successfully."

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


llm_agent = LLMAgent()
