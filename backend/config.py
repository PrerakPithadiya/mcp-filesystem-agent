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

# Workspace directory (strict sandbox root)
WORKSPACE_DIR = os.environ.get("WORKSPACE_DIR")
if WORKSPACE_DIR:
    WORKSPACE_PATH = Path(WORKSPACE_DIR).resolve()
else:
    WORKSPACE_PATH = (PROJECT_ROOT / "mcp-workspace").resolve()

WORKSPACE_PATH.mkdir(parents=True, exist_ok=True)

# LLM Configuration Helpers & Dynamic Reloading
def reload_env():
    """Reloads environment variables from .env files with override."""
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    load_dotenv(PROJECT_ROOT / "backend" / ".env", override=True)

def get_gemini_api_key() -> str:
    reload_env()
    return os.environ.get("GEMINI_API_KEY", "").strip()

def get_anthropic_api_key() -> str:
    reload_env()
    return os.environ.get("ANTHROPIC_API_KEY", "").strip()

def get_gemini_model() -> str:
    reload_env()
    return os.environ.get("GEMINI_MODEL", "gemini-3.6-flash").strip()

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
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
