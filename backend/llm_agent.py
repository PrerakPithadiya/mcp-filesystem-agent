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

2. Terse & Minimal Input Handling:
   - Understand short-hand notations accurately:
     * `filename.ext: some text` or `filename: some text` -> User wants to create or update that file with `some text`.
     * `todo: buy milk` -> Create or append to `todo.txt` with "buy milk".
     * `list`, `ls`, `dir`, `files` -> Call `list_folder("")` to list the workspace.
     * `read filename` or `cat filename` -> Call `read_file(filename)`.
     * `rm filename` or `delete filename` -> Call `delete_item(filename)`.
   - Never refuse a task just because the user wrote very little, as long as the intent is reasonably clear.

3. Ambiguity & Vague Input Protection (CRITICAL):
   - If the user gives a vague or underspecified command (such as simply "delete", "remove it", "read", "update") WITHOUT specifying which file/folder AND there is no clear target in recent conversation history:
     * DO NOT guess or pick a random file or folder!
     * DO NOT execute any random or destructive tools!
     * Ask the user politely which file or folder they would like to operate on.

4. Conversational Context & Pronoun Resolution:
   - When the user refers to "it", "that file", "the previous folder", or uses follow-up phrases (e.g. "now change it to...", "read it", "delete it"), resolve the reference from the conversation history.

5. Self-Correction & Error Recovery:
   - If calling `create_file` fails because the file already exists, and the user's intent was to set or write content to that file, automatically invoke `update_file` with mode="overwrite" to fulfill the request.
   - When deleting a folder, always ensure `recursive=True` so that folders with contents can be deleted after confirmation.

6. Sandboxing & Security:
   - All operations are strictly sandboxed inside the workspace. If an operation fails with a security violation or path traversal error (e.g., trying to access `../`), explain politely that access outside the safe workspace is strictly prohibited.

7. Keep responses concise, clear, and helpful. State clearly what was done or what confirmation is required.
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

            for tool_call in tool_use_blocks:
                tool_name = tool_call.name
                tool_input = tool_call.input

                # STAGE 4: Intercept delete_item for confirmation
                if tool_name == "delete_item":
                    conf_id = f"conf_{uuid.uuid4().hex[:8]}"
                    target_path = tool_input.get("path", "unknown")
                    try:
                        from server.sandbox import get_safe_path
                        safe_p = get_safe_path(target_path)
                        if safe_p.is_dir() and not tool_input.get("recursive"):
                            tool_input["recursive"] = True
                    except Exception:
                        pass
                    PENDING_CONFIRMATIONS[conf_id] = {
                        "tool": tool_name,
                        "arguments": tool_input,
                        "prompt": user_message,
                    }
                    requires_conf = True
                    conf_details = {
                        "id": conf_id,
                        "action": "delete_item",
                        "target": target_path,
                        "details": f"Delete '{target_path}'" + (" (and all sub-items)" if tool_input.get("recursive") else ""),
                    }
                    executed_tools.append({
                        "name": tool_name,
                        "arguments": tool_input,
                        "status": "pending_confirmation",
                        "result": "Awaiting user confirmation before deleting...",
                    })
                    # Do not execute now!
                    return {
                        "reply": f"⚠️ **Delete Confirmation Required**:\nAre you sure you want to permanently delete **`{target_path}`**? This action cannot be undone.",
                        "requires_confirmation": True,
                        "confirmation": conf_details,
                        "tool_calls": executed_tools,
                    }

                # Non-destructive tools: Execute immediately
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

            candidate_models = [config.GEMINI_MODEL, "gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"]
            models_to_try = list(dict.fromkeys(candidate_models))
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
                    response = chat.send_message(user_message)
                    break
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str:
                        logger.warning(f"Model {model_name} rate-limited: {err_str[:100]}... Trying fallback.")
                        import asyncio
                        await asyncio.sleep(1.5)
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

                for fc in response.function_calls:
                    tool_name = fc.name
                    tool_input = dict(fc.args) if fc.args else {}

                    # Intercept destructive delete_item action for confirmation
                    if tool_name == "delete_item":
                        conf_id = f"conf_{uuid.uuid4().hex[:8]}"
                        target_path = tool_input.get("path", "unknown")
                        try:
                            from server.sandbox import get_safe_path
                            safe_p = get_safe_path(target_path)
                            if safe_p.is_dir() and not tool_input.get("recursive"):
                                tool_input["recursive"] = True
                        except Exception:
                            pass
                        PENDING_CONFIRMATIONS[conf_id] = {
                            "tool": tool_name,
                            "arguments": tool_input,
                            "prompt": user_message,
                        }
                        executed_tools.append({
                            "name": tool_name,
                            "arguments": tool_input,
                            "status": "pending_confirmation",
                            "result": "Awaiting user confirmation before deleting...",
                        })
                        return {
                            "reply": f"⚠️ **Delete Confirmation Required**:\nAre you sure you want to permanently delete **`{target_path}`**? This action cannot be undone.",
                            "requires_confirmation": True,
                            "confirmation": {
                                "id": conf_id,
                                "action": "delete_item",
                                "target": target_path,
                                "details": f"Delete '{target_path}'" + (" (and all sub-items)" if tool_input.get("recursive") else ""),
                            },
                            "tool_calls": executed_tools,
                        }

                    # Execute non-destructive tool
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
                    response = chat.send_message(function_responses)
                else:
                    break

            return {
                "reply": response.text or "Operation completed successfully.",
                "tool_calls": executed_tools,
                "requires_confirmation": False,
            }

        except Exception as e:
            logger.error(f"Gemini API error: {e}", exc_info=True)
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

        target = action_data["arguments"].get("path", "item")

        if not confirmed:
            return {
                "reply": f"🛑 Deletion cancelled. **`{target}`** was not deleted.",
                "tool_calls": [{
                    "name": action_data["tool"],
                    "arguments": action_data["arguments"],
                    "status": "cancelled",
                    "result": "User cancelled deletion.",
                }],
                "requires_confirmation": False,
            }

        # User confirmed -> execute delete_item via MCP
        result_str = await mcp_client_service.call_tool(
            action_data["tool"], action_data["arguments"]
        )

        return {
            "reply": f"🗑️ Confirmed: {result_str}",
            "tool_calls": [{
                "name": action_data["tool"],
                "arguments": action_data["arguments"],
                "status": "success" if not result_str.startswith("Error") else "error",
                "result": result_str,
            }],
            "requires_confirmation": False,
        }


llm_agent = LLMAgent()
