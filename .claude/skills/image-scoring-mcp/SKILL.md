---
name: image-scoring-mcp
description: Vexlum Scoring MCP — compact search+dispatch on is-be-mcp / is-be-live and gallery is-ui-mcp / is-ui-live.
---

# Vexlum Scoring MCP server

**Compact contract:** [docs/technical/MCP_SEARCH_DISPATCH.md](../../../docs/technical/MCP_SEARCH_DISPATCH.md). Action registry: [`mcp/action_registry.json`](../../../mcp/action_registry.json). Full legacy index: [`.agent/mcp_tools_reference.md`](../../mcp_tools_reference.md). **Safe triage:** [`.agent/workflows/safe_mcp_diagnostics.md`](../../workflows/safe_mcp_diagnostics.md).

## Critical rules (is-be-mcp)

1. **Only two tools exist on compact MCP:** `search` and `dispatch`. There is no `execute_sql`, `get_error_summary`, or other raw tool name — those are **legacy** names from `modules/mcp_server.py` or AGENTS.md.
2. **Always `search` before `dispatch`** when the action is not already known. Use `search(..., include_schemas=True)` to read required args.
3. **`dispatch` takes `action_id` strings** in the form `category.name` (e.g. `diagnostics.get_error_summary`). Bare legacy names like `execute_sql` are accepted when they match `legacy_tool_name` in the registry.
4. **On `unknown_action`**, read `details.suggestions` and `details.hint` in the error envelope — do not guess another `category.tool` id from AGENTS.md.
5. **Writes / maintenance / `execute_code`** are not on compact stdio. Use **`is-be-live`** with `MCP_SSE_PROFILE=full` for the legacy ~54-tool surface.

## Setup

Copy [`.cursor/mcp.example.json`](../../../.cursor/mcp.example.json) → `.cursor/mcp.json`. Attach **`is-be-mcp`** (WSL + `~/.venvs/tf` via `run_mcp_compact_wsl.bat`); add **`is-be-live`** when WebUI is running.

## Preferred workflow (backend)

```text
search("why did scoring fail")                    # step 1 — required when unsure
dispatch("diagnostics.get_error_summary", {})     # step 2 — use action_id from search
```

## Compact dispatchable actions (is-be-mcp)

Regenerate from overlay: `python scripts/generate_mcp_tool_inventory.py --update-action-registry`.

| action_id | Use for |
|-----------|---------|
| `diagnostics.run_doctor` | `scripts/doctor.py` equivalent (`no_gpu`, `json`) |
| `diagnostics.get_error_summary` | Failed jobs, missing scores, stale running |
| `diagnostics.check_database_health` | Orphans, duplicates, integrity |
| `diagnostics.validate_config` | Config structure + optional DB ping |
| `diagnostics.get_database_engine_info` | Engine, connector, ping |
| `diagnostics.verify_environment` | Host, Python, deps |
| `diagnostics.get_model_status` | GPU / model load |
| `diagnostics.diagnose_phase_consistency` | **Requires `image_id`**; optional `folder_path` |
| `diagnostics.get_stale_running_phase_status` | IPS rows stuck `running` |
| `logs.read_debug_log` | Tail `debug.log` |
| `logs.get_server_log_tail` | Tail `webui.log` / `debug.log` |
| `logs.search_logs` | Regex grep on log tails |
| `config.get_config` | Redacted config |
| `jobs.get_failed_images` | Images **missing score columns** (not per-job failures) |
| `jobs.get_image_pipeline_failures` | **`job_image_actions` failed** for one image (`image_id` or `file_path`) |
| `jobs.get_run_diagnostics` | Post-run audit (`run_id`) |
| `jobs.get_runner_status` | In-process runners (WebUI process; often empty on stdio MCP) |
| `jobs.get_recent_jobs` | Job history |
| `jobs.get_job_details` | One job by `job_id` |
| `data.query_images` | Filtered listing (folder, scores, keywords) |
| `data.get_image_details` | Full row by `file_path` |
| `data.get_db_schema` | Postgres `information_schema` (before SQL) |
| `data.execute_sql` | Read-only `SELECT` / `WITH … SELECT` (`query`, optional `params`) |
| `data.get_embedding_stats` | Embedding coverage |
| `support.export_debug_bundle` | Redacted zip — `confirmed=True` |
| `browser.navigate` | Playwright — open URL (e.g. WebUI `http://127.0.0.1:7860/ui/`) |
| `browser.snapshot` | Playwright — accessibility page snapshot |
| `browser.click` | Playwright — click element (`target` from snapshot) |
| `browser.run_code_unsafe` | Playwright RCE — **`confirmed=True`** only |

### Common mistakes

| Wrong | Right |
|-------|-------|
| `dispatch("execute_sql", …)` without registry | `dispatch("data.execute_sql", …)` or legacy name `execute_sql` (resolved automatically) |
| `dispatch("data.execute_sql", …)` when not in registry | Run registry update; or `is-be-live` full profile |
| `dispatch("diagnostics.diagnose_phase_consistency", {"folder_path": "…"})` only | **Must include `image_id`**; use `data.query_images` to find candidates first |
| `jobs.get_failed_images` for one image job trace | `jobs.get_image_pipeline_failures` with `image_id` or `file_path` |
| Raw tool name from AGENTS.md inventory | `search("…")` → use returned `action_id` |

## Server keys

| Key | Tools |
|-----|-------|
| **`is-be-mcp`** | **`search`**, **`dispatch`** (stdio; WSL launcher default) |
| **`is-be-live`** | Same compact tools via SSE; **`MCP_SSE_PROFILE=full`** for legacy raw tools + `execute_code` |
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

### Per-image pipeline failure

```text
search("pipeline failures for image")
dispatch("jobs.get_image_pipeline_failures", {"file_path": "/mnt/d/Photos/…/DSC_0001.NEF"})
dispatch("data.get_image_details", {"file_path": "/mnt/d/Photos/…/DSC_0001.NEF"})
```

### Custom SQL (compact)

```text
search("execute sql")
dispatch("data.get_db_schema", {"table_name_prefix": "image"})
dispatch("data.execute_sql", {"query": "SELECT COUNT(*) FROM images WHERE …", "params": []})
```

### Export debug bundle

```text
search("export debug bundle")
dispatch("support.export_debug_bundle", {}, confirmed=True)
```

### Browser automation (Playwright via is-be-mcp)

No separate **`playwright`** MCP server — use **`browser.*`** actions:

```text
search("browser navigate webui")
dispatch("browser.navigate", {"url": "http://127.0.0.1:7860/ui/"}, dry_run=true)
dispatch("browser.snapshot", {})
```

Disable with `MCP_PLAYWRIGHT_ENABLED=0`. Regenerate registry: `node scripts/generate_playwright_registry.mjs`.

### Gallery + backend

1. **`is-ui-mcp`** → `search("gallery status")` → `dispatch("local.gallery_status", {})`
2. **`is-ui-mcp`** → `dispatch("api.api_health", {})` when backend WebUI is up
3. Pipeline/DB triage on **`is-be-mcp`**

## execute_code

Requires WebUI with **`MCP_SSE_PROFILE=full`** and **`ENABLE_MCP_EXECUTE_CODE=1`**. Assign to `result` to return a value.
