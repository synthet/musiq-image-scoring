---
name: image-scoring-mcp
description: Vexlum Scoring MCP — compact search+dispatch on is-be-mcp / is-be-webui and gallery is-ui-mcp / is-ui-live.
---

# Vexlum Scoring MCP server

**Compact contract:** [docs/technical/MCP_SEARCH_DISPATCH.md](../../../docs/technical/MCP_SEARCH_DISPATCH.md). Action registry: [`mcp/action_registry.json`](../../../mcp/action_registry.json). Full index: [`.agent/mcp_tools_reference.md`](../../mcp_tools_reference.md). **Safe triage:** [`.agent/workflows/safe_mcp_diagnostics.md`](../../workflows/safe_mcp_diagnostics.md).

## Setup

Copy [`.cursor/mcp.example.json`](../../../.cursor/mcp.example.json) → `.cursor/mcp.json`. Attach **`is-be-mcp`** (WSL + `~/.venvs/tf` via `run_mcp_compact_wsl.bat`); add **`is-be-webui`** when WebUI is running.

## Preferred workflow (backend)

1. **`is-be-mcp`** or **`is-be-webui`** → **`search(query)`**
2. **`dispatch(action_id, arguments)`**

Example: `search("why did scoring fail")` → `dispatch("diagnostics.get_error_summary", {})`.

Use **`search(..., include_schemas=True)`** when you need full argument schemas before dispatch.

## Server keys

| Key | Tools |
|-----|-------|
| **`is-be-mcp`** | **`search`**, **`dispatch`** (stdio; WSL launcher default) |
| **`is-be-webui`** | Same compact tools via SSE; **`MCP_SSE_PROFILE=full`** for legacy raw tools + `execute_code` |
| **`is-ui-mcp`** | Gallery — **`search`**, **`dispatch`** |
| **`is-ui-live`** | Gallery SSE — live IPC when Electron dev is running |

Legacy profile servers (`is-be-diag`, `is-ui-router`, …) are **not** in default configs.

## Workflows

### Debug scoring failure

```text
search("scoring failure")
dispatch("diagnostics.get_error_summary", {})
dispatch("jobs.get_failed_images", {"limit": 20})
dispatch("logs.search_logs", {"pattern": "error|failed"})
```

### Export debug bundle

```text
search("export debug bundle")
dispatch("support.export_debug_bundle", {}, confirmed=True)
```

### Gallery + backend

1. **`is-ui-mcp`** → `search("gallery status")` → `dispatch("local.gallery_status", {})`
2. **`is-ui-mcp`** → `dispatch("api.api_health", {})` when backend WebUI is up
3. Pipeline/DB triage on **`is-be-mcp`**

## execute_code

Requires WebUI with **`MCP_SSE_PROFILE=full`** and **`ENABLE_MCP_EXECUTE_CODE=1`**. Assign to `result` to return a value.
