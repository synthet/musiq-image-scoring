---
type: Guide
title: Compact MCP servers (is-be-mcp / is-ui-mcp)
description: Unified Node stdio entrypoint, sse_status probe, resilient SSE proxy, and multi-root Cursor workspace setup for backend and gallery MCP.
resource: docs/guides/setup/mcp-compact-servers.md
tags: [mcp, agents, cursor, setup, gallery-docs, cross-repo]
timestamp: 2026-06-20T00:00:00Z
okf_version: 0.1
---

# Compact MCP servers (is-be-mcp / is-ui-mcp)

Both **image-scoring-backend** and **image-scoring-gallery** expose the same compact MCP surface to Cursor:

| Tool | Purpose |
|------|---------|
| **`search`** | BM25 over the repo action registry (including **`browser.*`** Playwright actions); no side effects |
| **`dispatch`** | Execute an action by `action_id` with schema validation |
| **`sse_status`** | Read-only probe of the optional live SSE server |

Shared contract details: [MCP_SEARCH_DISPATCH.md](../../technical/MCP_SEARCH_DISPATCH.md).

## Cursor entrypoint (both repos)

Copy [`.cursor/mcp.example.json`](../../../.cursor/mcp.example.json) → `.cursor/mcp.json` (gitignored). Default config uses **stdio only** — no SSE keys — so MCP still loads when WebUI/Electron is down.

```json
{
  "mcpServers": {
    "is-be-mcp": {
      "command": "node",
      "args": ["mcp-server/dist/compactIndex.js"],
      "cwd": "${workspaceFolder:image-scoring-backend}"
    }
  }
}
```

Gallery uses the same shape with `is-ui-mcp` and `"cwd": "${workspaceFolder:image-scoring-gallery}"`.

**Multi-root workspace:** name folders in `image-scoring-backend.code-workspace` (`image-scoring-backend`, `image-scoring-gallery`, …) so `${workspaceFolder:…}` resolves correctly. Pair template: [`.cursor/mcp.pair.example.json`](../../../.cursor/mcp.pair.example.json).

## Build

| Repo | Command |
|------|---------|
| **Backend** | `cd mcp-server && npm install && npm run build` |
| **Gallery** | `cd mcp-server && npm install && npm run build:registry` |

Reload MCP in Cursor after every build (toggle servers off/on or restart Cursor).

## Architecture

```text
Cursor  →  node mcp-server/dist/compactIndex.js  (stdio)
              ├─ search / dispatch / sse_status
              ├─ Backend: Python worker (WSL + ~/.venvs/tf on Windows)
              ├─ Browser: Playwright MCP child (lazy spawn via npx @playwright/mcp)
              └─ Gallery: TypeScript handlers + optional SSE proxy to is-ui-live
```

| Server key | Stdio always? | Optional SSE | SSE URL | Graceful error |
|------------|---------------|--------------|---------|----------------|
| **`is-be-mcp`** | Yes | **`is-be-live`** | `http://127.0.0.1:7860/mcp/sse` | `webui_unavailable` |
| **`is-ui-mcp`** | Yes | **`is-ui-live`** | `http://127.0.0.1:9373/mcp/sse` | `live_unavailable` |

Add SSE entries **only while** WebUI or Electron dev is running. Stdio servers proxy selected `dispatch` calls when SSE is up.

### Backend Python bridge

Node registers MCP tools; a persistent **`scripts/mcp/compact_worker.py`** child (via WSL + `~/.venvs/tf` on Windows) runs search/dispatch/sse_status using [`modules/mcp/compact_tools.py`](../../../modules/mcp/compact_tools.py). Legacy pure-Python stdio: `scripts/batch/run_mcp_proxy_wsl.bat`.

Env overrides: `IS_BE_MCP_USE_WSL`, `IS_BE_MCP_VENV_ACTIVATE`, `IS_BE_MCP_WORKER_SHELL`. Proxy allowlists: `MCP_WEBUI_PROXY_ACTION_IDS`, `MCP_WEBUI_PROXY_PREFIXES`. Playwright: `MCP_PLAYWRIGHT_ENABLED=0` to disable; `MCP_PLAYWRIGHT_PACKAGE` (default `@playwright/mcp@latest`).

### Playwright browser actions (is-be-mcp)

Browser automation is folded into **`is-be-mcp`** — no separate `playwright` MCP key. Registry: [`mcp/actions/playwright_registry.json`](../../../mcp/actions/playwright_registry.json) (generated from [`mcp/actions/playwright_tools/`](../../../mcp/actions/playwright_tools/)).

```text
search("browser navigate webui")
dispatch("browser.navigate", {"url": "http://127.0.0.1:7860/ui/"}, dry_run=true)
dispatch("browser.snapshot", {})
```

Live browser dispatch spawns a Playwright MCP child on first use. `browser.run_code_unsafe` requires `confirmed=True`.

Parallel MCP tool calls are safe: each request carries a UUID; the Python worker echoes `_request_id` on every response line.

### Gallery live actions

- **`local.*` / `api.*`** — handled in Node.
- **`live_ipc`** — proxied to **`is-ui-live`** when Electron SSE is up.
- **`live_cdp`** (click, fill, wait_for, …) — CDP in Node when Electron remote debugging is up; optional `MCP_LIVE_PROXY_PREFIXES=live.` forces SSE.

## Verification (MCP protocol)

```text
sse_status()                                    → ok + url + server key
search("database health")                       → backend action hits
search("gallery status")                        → gallery action hits
search("browser navigate")                      → browser.* Playwright actions
dispatch("diagnostics.check_database_health", dry_run=true)
dispatch("local.gallery_status", dry_run=true)
dispatch("browser.navigate", {"url": "http://127.0.0.1:7860/ui/"}, dry_run=true)
```

## Other agents (Claude Code, Antigravity, Codex)

Same compact surface — copy the repo **example** into the agent’s local config (gitignored). Do **not** add a standalone **`playwright`** MCP server; browser automation is **`browser.*`** on **`is-be-mcp`** via **`dispatch`**.

| Agent | Backend example | Gallery example |
|-------|-----------------|-----------------|
| **Claude Code** | [`.mcp.json.example`](../../../.mcp.json.example) → `.mcp.json` | [`.mcp.json.example`](https://github.com/synthet/image-scoring-gallery/blob/main/.mcp.json.example) |
| **Antigravity** | [`mcp_config.example.json`](../../../mcp_config.example.json) | [`mcp_config.example.json`](https://github.com/synthet/image-scoring-gallery/blob/main/mcp_config.example.json) |
| **Codex** | [`.codex/config.example.toml`](../../../.codex/config.example.toml) | [`.codex/config.example.toml`](https://github.com/synthet/image-scoring-gallery/blob/main/.codex/config.example.toml) |

Multi-root (backend + gallery open together): **`mcp_config.pair.example.json`** / **`.codex/config.pair.example.toml`** in each repo. Claude permissions template: [`.claude/settings.json.example`](../../../.claude/settings.json.example) (compact tools only; **`playwright`** in `disabledMcpjsonServers`).

## Related

- [MCP_SEARCH_DISPATCH.md](../../technical/MCP_SEARCH_DISPATCH.md) — search/dispatch envelopes and action catalog
- [AGENT_COORDINATION.md](../../technical/AGENT_COORDINATION.md) — cross-repo coordination
- [DIAGNOSTICS.md](../../DIAGNOSTICS.md) — doctor and MCP triage workflows
- [AGENTS.md](../../../AGENTS.md) — tool inventory and server keys
- Gallery operator mirror: [05-mcp-compact-servers.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/guides/05-mcp-compact-servers.md)
