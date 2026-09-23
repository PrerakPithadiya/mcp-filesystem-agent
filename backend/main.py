"""
FastAPI Backend Server
Exposes endpoints for chat, tool execution, delete confirmation, and live workspace file tree.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from backend import config
from backend.llm_agent import llm_agent
from backend.mcp_client import mcp_client_service
from server.sandbox import get_default_workspace, get_safe_path

app = FastAPI(
    title="MCP Filesystem Chatbot API",
    description="Backend connecting Google Gemini AI to Python FastMCP Server with safe sandboxing.",
    version="1.0.0",
)

# Enable CORS for local Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, Any]]] = []


class ConfirmRequest(BaseModel):
    confirmation_id: str
    confirmed: bool


@app.get("/api/health")
async def health_check():
    """Returns server status, active provider, and configured model."""
    workspace = get_default_workspace()
    return {
        "status": "online",
        "provider": config.LLM_PROVIDER,
        "model": config.GEMINI_MODEL if config.LLM_PROVIDER == "gemini" else config.CLAUDE_MODEL,
        "has_gemini_key": bool(config.GEMINI_API_KEY),
        "has_anthropic_key": bool(config.ANTHROPIC_API_KEY),
        "workspace": str(workspace),
        "workspace_name": workspace.name,
    }


@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    """
    Main conversational endpoint. Sends message to Gemini, handles tool calls via FastMCP,
    and prompts for confirmation on destructive actions.
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    result = await llm_agent.chat(req.message, req.history or [])
    return result


@app.post("/api/chat/stream")
async def chat_stream_endpoint(req: ChatRequest):
    """
    Streaming chat endpoint using Server-Sent Events (SSE).
    Streams real-time agent status, tool execution, file diffs, and LLM text tokens.
    """
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    async def event_generator():
        try:
            async for event_chunk in llm_agent.chat_stream(req.message, req.history or []):
                yield event_chunk
        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/confirm")
async def confirm_endpoint(req: ConfirmRequest):
    """
    Endpoint to confirm or cancel a pending deletion action.
    """
    result = await llm_agent.resolve_confirmation(req.confirmation_id, req.confirmed)
    return result


PROTECTED_SYSTEM_NAMES = {"desktop.ini", "thumbs.db", ".ds_store", "$recycle.bin"}


def _build_tree(directory: Path, base_dir: Path) -> Dict[str, Any]:
    """Helper to build recursive JSON tree of workspace files and folders."""
    relative_path = str(directory.relative_to(base_dir)).replace("\\", "/")
    if relative_path == ".":
        relative_path = ""

    children = []
    try:
        entries = sorted(
            [p for p in directory.iterdir() if p.name.lower() not in PROTECTED_SYSTEM_NAMES],
            key=lambda p: (not p.is_dir(), p.name.lower())
        )
        for entry in entries:
            if entry.is_dir():
                children.append(_build_tree(entry, base_dir))
            else:
                rel = str(entry.relative_to(base_dir)).replace("\\", "/")
                children.append({
                    "name": entry.name,
                    "path": rel,
                    "type": "file",
                    "size": entry.stat().st_size,
                })
    except Exception:
        pass

    return {
        "name": directory.name if relative_path else (directory.name or "workspace"),
        "path": relative_path,
        "type": "directory",
        "children": children,
    }


@app.get("/api/workspace/tree")
async def get_workspace_tree():
    """
    Returns full hierarchy of files and folders inside mcp-workspace/ for the live UI explorer.
    """
    workspace = get_default_workspace()
    tree = _build_tree(workspace, workspace)
    return tree


@app.get("/api/workspace/file")
async def get_file_content(path: str):
    """
    Returns the content of a file in the workspace for preview in the UI.
    """
    try:
        safe = get_safe_path(path)
        if not safe.exists() or not safe.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        content = safe.read_text(encoding="utf-8")
        return {"path": path, "content": content, "size": safe.stat().st_size}
    except PermissionError as pe:
        raise HTTPException(status_code=403, detail=str(pe))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/workspace/reset")
async def reset_workspace():
    """
    Resets the workspace with sample demo files for demonstration.
    """
    workspace = get_default_workspace()
    import shutil
    for item in workspace.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()

    # Create a nice sample file
    sample = workspace / "welcome.txt"
    sample.write_text("Welcome to MCP Filesystem!\nAsk me to create, edit, or explore files.\n", encoding="utf-8")

    return {"message": "Workspace reset successfully with sample welcome.txt"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host=config.HOST, port=config.PORT, reload=True)
