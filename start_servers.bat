@echo off
echo ===================================================
echo   Starting MCP Filesystem AI Chatbot Servers
echo ===================================================

echo [1/2] Launching FastAPI Backend on http://127.0.0.1:8000 ...
start "MCP Backend (FastAPI)" cmd /k "cd /d "%~dp0" && .\venv\Scripts\activate && python -m uvicorn backend.main:app --reload --port 8000"

echo [2/2] Launching Vite Frontend on http://localhost:5173 ...
start "MCP Frontend (Vite)" cmd /k "cd /d "%~dp0frontend" && npm run dev"

echo.
echo Both servers are launching!
echo Backend: http://127.0.0.1:8000
echo Frontend: http://localhost:5173
echo ===================================================
