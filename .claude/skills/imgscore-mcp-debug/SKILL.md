---
name: imgscore-mcp-debug
description: Routine read-only debugging for the image-scoring Python backend via MCP—is-be-mcp search+dispatch, scoring/tagging failures, job errors, Postgres questions, DB integrity, and config sanity.
---

# imgscore-mcp-debug

Read-only triage for **image-scoring-backend** using MCP. **Do not** mutate DB/config unless the user explicitly asks.

## Preferred entry

**`is-be-mcp`**: **`search(query)`** → **`dispatch(action_id, arguments)`**. Contract: [MCP_SEARCH_DISPATCH.md](../../../docs/technical/MCP_SEARCH_DISPATCH.md).

## Server keys

| Key | Use |
|-----|-----|
| **`is-be-mcp`** | **Default** — `search`, `dispatch` |
| **`is-be-webui`** | Legacy tools not yet on compact dispatch; `execute_code` when enabled |

Gallery sibling: **`is-ui-local`** `gallery_status`, **`is-ui-api`** `api_*`.

## Start here

1. **`search`**("scoring errors") → **`dispatch("diagnostics.get_error_summary", {})`**
2. **`dispatch("diagnostics.check_database_health", {})`**, **`dispatch("diagnostics.validate_config", {})`**
3. **`dispatch("jobs.get_failed_images", {"limit": 20})`**, **`dispatch("jobs.get_run_diagnostics", {"run_id": N})`** when run id known
4. **`dispatch("logs.search_logs", {"pattern": "error|failed"})`**, **`dispatch("logs.read_debug_log", {"lines": 100})`**

## High-risk (avoid unless asked)

On **`is-be-webui`** SSE: `execute_code`, `run_processing_job`, `set_config_value`, `prune_missing_files`, …

## References

- [AGENTS.md](../../../AGENTS.md)
- [MCP_SEARCH_DISPATCH.md](../../../docs/technical/MCP_SEARCH_DISPATCH.md)
- [.agent/mcp_tools_reference.md](../../mcp_tools_reference.md)
- [workflows/safe_mcp_diagnostics.md](../../workflows/safe_mcp_diagnostics.md)
