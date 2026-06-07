---
name: image-scoring-mcp
description: Vexlum Scoring MCP — compact search+dispatch (is-be-mcp), legacy domain servers, gallery is-ui-*, execute_code via is-be-webui.
---

# Vexlum Scoring MCP server

Tools are registered in [`modules/mcp_server.py`](../../../modules/mcp_server.py). **Compact contract:** [docs/technical/MCP_SEARCH_DISPATCH.md](../../../docs/technical/MCP_SEARCH_DISPATCH.md). Action registry: [`mcp/action_registry.json`](../../../mcp/action_registry.json). Full index: [`mcp_tools_reference.md`](../../mcp_tools_reference.md). **Safe triage:** [workflows/safe_mcp_diagnostics.md](../../workflows/safe_mcp_diagnostics.md).

## Preferred workflow (backend)

1. **`is-be-mcp`** → **`search(query)`**
2. **`dispatch(action_id, arguments)`**

Example: `search("why did scoring fail")` → `dispatch("diagnostics.get_error_summary", {})`.

## Naming

| Prefix | Repo | Entry |
|--------|------|-------|
| **`is-be-mcp`** | backend | **`search`**, **`dispatch`** (preferred) |
| **`is-be-*`** | backend | Legacy domain tools |
| **`is-ui-*`** | gallery | **`ui_find`** on **`is-ui-router`** |

Use **`is-be-*`** and **`is-ui-*`** keys only; drop legacy MCP server names from user configs.

## Server keys (backend)

| Key | Tools (examples) |
|-----|------------------|
| **`is-be-mcp`** | `search`, `dispatch` |
| **`is-be-router`** | `search`, `dispatch`, deprecated `be_find` |
| **`is-be-diag`** | Legacy: `get_error_summary`, `search_logs` |
| **`is-be-jobs`** | Legacy: `get_failed_images`, `get_run_diagnostics` |
| **`is-be-data`** | Legacy: `query_images`, `get_embedding_stats` |
| **`is-be-webui`** | SSE; `execute_code` when `ENABLE_MCP_EXECUTE_CODE=1` |

## execute_code

SSE only on **`is-be-webui`**. Set **`ENABLE_MCP_EXECUTE_CODE=1`** on WebUI process.
