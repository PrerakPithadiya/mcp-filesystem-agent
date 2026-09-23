"""
Configuration settings for the MCP Filesystem backend.
Loads environment variables and sets sensible defaults.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Root project directory
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env file from project root or backend dir (override=True ensures .env values take precedence)
load_dotenv(PROJECT_ROOT / ".env", override=True)
load_dotenv(PROJECT_ROOT / "backend" / ".env", override=True)

# LLM Configuration Helpers & Dynamic Reloading
def reload_env():
    """Reloads environment variables from .env files with override, preserving runtime WORKSPACE_DIR."""
    saved_workspace = os.environ.get("WORKSPACE_DIR")
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    load_dotenv(PROJECT_ROOT / "backend" / ".env", override=True)
    if saved_workspace is not None:
        os.environ["WORKSPACE_DIR"] = saved_workspace


def get_workspace_path() -> Path:
    """Returns resolved workspace path from WORKSPACE_DIR or default sandbox folder."""
    workspace_dir = os.environ.get("WORKSPACE_DIR")
    if workspace_dir:
        path = Path(workspace_dir).resolve()
    else:
        path = (PROJECT_ROOT / "mcp-workspace").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


# Workspace directory (strict sandbox root)
WORKSPACE_PATH = get_workspace_path()

def get_gemini_api_key() -> str:
    reload_env()
    return os.environ.get("GEMINI_API_KEY", "").strip()

def get_anthropic_api_key() -> str:
    reload_env()
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()

def get_gemini_model() -> str:
    reload_env()
    return os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()

def get_llm_provider() -> str:
    reload_env()
    provider_from_env = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if provider_from_env:
        return provider_from_env
    if get_gemini_api_key():
        return "gemini"
    if get_anthropic_api_key():
        return "anthropic"
    return "gemini"

# Server settings
PORT = int(os.environ.get("PORT", 8000))
HOST = os.environ.get("HOST", "127.0.0.1")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

def __getattr__(name: str):
    """Dynamic fallback for module attributes to ensure .env changes are always reflected."""
    if name == "GEMINI_API_KEY":
        return get_gemini_api_key()
    elif name == "ANTHROPIC_API_KEY":
        return get_anthropic_api_key()
    elif name == "GEMINI_MODEL":
        return get_gemini_model()
    elif name == "LLM_PROVIDER":
        return get_llm_provider()
    elif name == "WORKSPACE_PATH":
        return get_workspace_path()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
