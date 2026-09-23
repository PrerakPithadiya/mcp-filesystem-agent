# Project State

## Goal

An interactive, full-stack AI filesystem chatbot powered by Google Gemini and the Model Context Protocol (MCP). Built with Python FastMCP, FastAPI, and React + Tailwind CSS, it enables users to safely manage local sandboxed files via natural language with real-time UI file tree sync, strict sandbox security, and human confirmation gates for destructive actions.

## Commands

- test: `.\venv\Scripts\python -m unittest discover tests`
- benchmark: `.\venv\Scripts\python scripts/run_full_suite.py`
- build: `cd frontend && npm run build`
- dev-backend: `.\venv\Scripts\activate && uvicorn backend.main:app --reload --port 8000`
- dev-frontend: `cd frontend && npm run dev`
- launcher: `.\start_servers.bat`

## Task board

- [x] done: Initial MCP filesystem server & sandbox implementation (merged 2026-09-19)
- [x] done: FastMCP JSON-RPC client integration & Gemini tool orchestration (PR #2, merged 2026-09-19)
- [x] done: Linear-style dark theme UI overhaul with brass accents & real-time file tree animation (PR #3, merged 2026-09-19)
- [x] done: 120-prompt automated benchmark runner & evaluation suite (PR #4, merged 2026-09-19)
- [x] done: One-click Windows starter script & README documentation sync (PR #5, merged 2026-09-19)
- [x] done: Fix natural phrasing edge cases in nonexistent file test (PR #6, merged 2026-09-19)
- [x] done: Initialize autonomous git workflow and project state tracker (merged 2026-09-19)
- [x] done: Direct Windows Desktop workspace support with system file protection and dynamic UI sync (2026-09-23)
- [x] done: Real-time SSE token streaming, agent step badges, visual file diff & code preview modal (merged 2026-09-23)
- [ ] todo: Session persistence across page reloads (chat history & state caching)

## Active branches

- main | production / integration branch | clean

## Decisions

- 2026-09-23 | Real-time SSE Streaming & Visual File Diffs | Implemented /api/chat/stream SSE pipeline with live agent lifecycle stages, diff computation via Python difflib, and full code preview modal.
- 2026-09-23 | Option A: Windows Desktop Workspace via WORKSPACE_DIR | Enables direct Windows Desktop CRUD operations with protected system file exclusions (desktop.ini) and UI dynamic workspace sync.
- 2026-09-19 | Adopt autonomous git workflow rule (`autonomous-git-workflow.md`) | Streamlines solo development with automated branch creation, testing gates, and seamless merges into `main`.
- 2026-09-19 | Decompose monolithic PR #1 into 4 modular feature branches (#2, #3, #4, #5) | Ensures clean separation of concerns, independent reviewability, and healthy Git history.
- 2026-09-19 | Use Linear dark navy palette (`#0F1419`) with warm brass accent (`#C9A659`) | Elevates developer tool feel over generic AI templates.

## Pending approvals

(None)

## Known issues / follow-ups

- Explore Server-Sent Events (SSE) to stream Gemini text tokens rather than waiting for full turn completion.
