---
description: Launch FastAPI + Gradio WebUI (Vexlum Scoring)
---

## Purpose

Start the **WebUI** on the default port (typically **7860**) with FastAPI + Gradio and optional MCP.

## When to use

- Local development, manual API checks, SSE MCP with Cursor.

## Canonical docs first

- [docs/DEVELOPMENT.md](../../docs/DEVELOPMENT.md)
- [AGENTS.md](../../AGENTS.md) — MCP SSE URL, `execute_code` flag
- [.cursor/rules/python-wsl-webapp-env.mdc](../../.cursor/rules/python-wsl-webapp-env.mdc)

## Safe commands

**Windows (recommended):** from repo root, `run_webui.bat` (launches WSL with venv + Firebird `LD_LIBRARY_PATH` when needed).

**WSL (repo root):**

```bash
export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:$(pwd)/FirebirdLinux/Firebird-5.0.0.1306-0-linux-x64/opt/firebird/lib
source ~/.venvs/tf/bin/activate
python webui.py
# or: python launch.py
```

**MCP alongside WebUI (optional):**

```bash
ENABLE_MCP_SERVER=1 python webui.py
```

**SSE note:** MCP `execute_code` uses the SSE transport; see `GET /mcp-status` on the running app for `expected_sse_url`.

## Checks

- Browser: `http://127.0.0.1:7860` (or port shown in terminal).
- Optional: `GET http://127.0.0.1:<port>/mcp-status` for MCP diagnostics.

## Common failure modes

- Port in use; Postgres down; wrong `config.json` `database.engine`.

## Do not

- Do not assume SQLite-only workflows for current deployments.
