"""
MCP Client Module
Manages communication with the FastMCP server via Stdio transport.
Provides tool discovery, schema translation, and tool execution.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from backend.config import PROJECT_ROOT, WORKSPACE_PATH

logger = logging.getLogger("mcp_client")
logging.basicConfig(level=logging.INFO)


class MCPClientService:
    def __init__(self, workspace_path: Optional[Path] = None):
        self._workspace_path = workspace_path
        self.server_script = PROJECT_ROOT / "server" / "mcp_server.py"
        self._tools_cache: Optional[List[Dict[str, Any]]] = None
        self._lock = asyncio.Lock()

    @property
    def workspace_path(self) -> Path:
        env_root = os.environ.get("WORKSPACE_DIR")
        if env_root:
            return Path(env_root).resolve()
        return self._workspace_path or WORKSPACE_PATH

    def get_server_params(self) -> StdioServerParameters:
        """Returns standard I/O parameters for launching the FastMCP server child process."""
        env = os.environ.copy()
        env["WORKSPACE_DIR"] = str(self.workspace_path)
        env["PYTHONPATH"] = f"{str(PROJECT_ROOT)}{os.pathsep}{env.get('PYTHONPATH', '')}"

        return StdioServerParameters(
            command=sys.executable,
            args=["-m", "server.mcp_server"],
            env=env,
        )

    async def _execute_via_stdio(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Runs a single tool call via stdio session."""
        params = self.get_server_params()
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(tool_name, arguments)
                output_parts = []
                if hasattr(result, "content") and result.content:
                    for item in result.content:
                        if hasattr(item, "text"):
                            output_parts.append(item.text)
                        else:
                            output_parts.append(str(item))
                elif hasattr(result, "text"):
                    output_parts.append(result.text)
                else:
                    output_parts.append(str(result))
                return "\n".join(output_parts)

    async def list_tools(self) -> List[Dict[str, Any]]:
        """Discovers tools exposed by the MCP server and returns their metadata."""
        if self._tools_cache:
            return self._tools_cache

        async with self._lock:
            if self._tools_cache:
                return self._tools_cache

            try:
                params = self.get_server_params()
                async with stdio_client(params) as (read_stream, write_stream):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        tools_result = await session.list_tools()
                        parsed_tools = []
                        for tool in tools_result.tools:
                            parsed_tools.append({
                                "name": tool.name,
                                "description": tool.description or "",
                                "input_schema": tool.inputSchema if hasattr(tool, "inputSchema") else getattr(tool, "input_schema", {}),
                            })
                        self._tools_cache = parsed_tools
                        return self._tools_cache
            except Exception as e:
                logger.warning(f"Note: querying tools via stdio: {e}. Using direct schemas.")
                self._tools_cache = self._get_fallback_tool_definitions()
                return self._tools_cache

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Calls a tool on the MCP server. Tries stdio first, falls back gracefully if needed."""
        async with self._lock:
            try:
                # Add 5s timeout on stdio subprocess to avoid hanging on Windows
                return await asyncio.wait_for(self._execute_via_stdio(tool_name, arguments), timeout=8.0)
            except Exception as e:
                logger.info(f"Using direct FastMCP tool execution (stdio fallback): {e}")
                return await self._direct_tool_fallback(tool_name, arguments)

    async def _direct_tool_fallback(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Direct fallback execution in case of subprocess stdio issue on Windows."""
        from server import mcp_server
        func = getattr(mcp_server, tool_name, None)
        if not func:
            return f"Error: Tool '{tool_name}' not found."
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(**arguments)
            return func(**arguments)
        except Exception as e:
            return f"Error executing '{tool_name}': {str(e)}"

    def _get_fallback_tool_definitions(self) -> List[Dict[str, Any]]:
        """Tool definitions matching server/mcp_server.py."""
        return [
            {
                "name": "create_folder",
                "description": "Create a new folder inside the safe workspace.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "folder_path": {"type": "string", "description": "Relative path of folder to create (e.g. 'Projects')"}
                    },
                    "required": ["folder_path"],
                },
            },
            {
                "name": "create_file",
                "description": "Create a new text file with content inside the safe workspace.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Relative path of file to create (e.g. 'notes.txt')"},
                        "content": {"type": "string", "description": "Text content for the file"}
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "read_file",
                "description": "Read and return the text content of a file inside the safe workspace.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Relative path of file to read"}
                    },
                    "required": ["file_path"],
                },
            },
            {
                "name": "list_folder",
                "description": "List files and subfolders inside a folder in the safe workspace.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "folder_path": {"type": "string", "description": "Relative path to list (empty or '.' for root)"}
                    },
                },
            },
            {
                "name": "update_file",
                "description": "Update or append content to an existing file in the safe workspace.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_path": {"type": "string", "description": "Relative path of file to update"},
                        "content": {"type": "string", "description": "New content to write"},
                        "mode": {"type": "string", "enum": ["overwrite", "append"], "description": "Mode: 'overwrite' or 'append'"}
                    },
                    "required": ["file_path", "content"],
                },
            },
            {
                "name": "delete_item",
                "description": "Permanently delete a file or folder from the safe workspace.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path of file or folder to delete"},
                        "recursive": {"type": "boolean", "description": "Set True to delete non-empty folder"}
                    },
                    "required": ["path"],
                },
            },
        ]


# Singleton instance
mcp_client_service = MCPClientService()
