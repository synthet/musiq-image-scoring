---
name: image-scoring-mcp
description: Vexlum Scoring MCP — compact search+dispatch on is-be-mcp, gallery is-ui-*, legacy tools via is-be-webui SSE.
---

# Vexlum Scoring MCP server

Tools are registered in [`modules/mcp_server.py`](../../../modules/mcp_server.py). **Compact contract:** [docs/technical/MCP_SEARCH_DISPATCH.md](../../../docs/technical/MCP_SEARCH_DISPATCH.md). Action registry: [`mcp/action_registry.json`](../../../mcp/action_registry.json). Full index: [`.agent/mcp_tools_reference.md`](../../mcp_tools_reference.md). **Safe triage:** [`.agent/workflows/safe_mcp_diagnostics.md`](../../workflows/safe_mcp_diagnostics.md).

## Setup

Copy [`.cursor/mcp.example.json`](../../../.cursor/mcp.example.json) → `.cursor/mcp.json`. Attach **`is-be-mcp`**; add **`is-be-webui`** when WebUI is running.

## Preferred workflow (backend)

1. **`is-be-mcp`** → **`search(query)`**
2. **`dispatch(action_id, arguments)`**

Example: `search("why did scoring fail")` → `dispatch("diagnostics.get_error_summary", {})`.

## Server keys

| Key | Tools |
|-----|-------|
| **`is-be-mcp`** | **`search`**, **`dispatch`** |
| **`is-be-webui`** | All legacy tools via SSE; `execute_code` when `ENABLE_MCP_EXECUTE_CODE=1` |
| **`is-ui-router`** | Gallery — `ui_find` |
| **`is-ui-local`** | Gallery — `gallery_status`, logs, config |
| **`is-ui-api`** | Gallery — `api_*` when backend up |
| **`is-ui-live`** | Gallery SSE — `cdp_*`, window status |

Unlisted legacy profile servers (`is-be-diag`, `is-be-jobs`, …) are **not** in the default config. Use compact dispatch or **`is-be-webui`**.

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

1. **`is-ui-local`** → `gallery_status`
2. **`is-ui-api`** → `api_health` if backend up
3. Backend triage on **`is-be-mcp`**

## execute_code

SSE only on **`is-be-webui`**. Set **`ENABLE_MCP_EXECUTE_CODE=1`**. Assign to `result` to return a value.
