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
| **`is-be-live`** | Legacy raw tools via `MCP_SSE_PROFILE=full`; `execute_code` when enabled |

Gallery sibling: **`is-ui-local`** `gallery_status`, **`is-ui-api`** `api_*`.

## Start here

1. **`search`**("scoring errors") → **`dispatch("diagnostics.get_error_summary", {})`**
2. **`dispatch("diagnostics.check_database_health", {})`**, **`dispatch("diagnostics.validate_config", {})`**
3. **`dispatch("jobs.get_failed_images", {"limit": 20})`**, **`dispatch("jobs.get_run_diagnostics", {"run_id": N})`** when run id known
4. **`dispatch("logs.search_logs", {"pattern": "error|failed"})`**, **`dispatch("logs.read_debug_log", {"lines": 100})`**

## High-risk (avoid unless asked)

On **`is-be-live`** SSE: `execute_code`, `run_processing_job`, `set_config_value`, `prune_missing_files`, …

## HTTP fallback when MCP is down

When **`is-be-mcp`** fails live discovery, probe the WebUI REST API directly (prefer `curl.exe` + file bodies on Windows — see [`agent-data-config`](../agent-data-config/SKILL.md)).

**Confirmed read endpoints:**

| Method | Path | Use |
|--------|------|-----|
| GET | `/api/health` | Liveness (`200`) — **not** `/api/status/health` (404) |
| GET | `/api/runs/drive/status` | Auto-drive enabled / last tick / outstanding |
| GET | `/api/jobs/queue` | `queue_size`, `active_runner` |
| GET | `/api/jobs/recent?limit=N` | Recent job status |
| GET | `/api/runs/folder-buckets?limit=N&offset=0` | Planner buckets / phase progress |

**Writes (need user intent):** `POST /api/runs/drive/start`, `POST /api/runs/drive/stop`.

**Do not guess these paths:**

- `/api/status/health` → 404
- `/api/runs/drive/diagnostics` → matches `/api/runs/{run_id}/diagnostics` and fails `int_parsing` on `run_id`

**Queue-cleared condition** (for "process the queue until done"):

1. `folder-buckets` `total == 0` with no `awaiting_*` or `in_flight` buckets
2. `jobs/queue` `queue_size == 0` and `active_runner == null`

Completed scoring / culling / keywords jobs alone are **not** enough — folders can remain at `awaiting_bird_species` afterward. Full-pipeline `target_phases` include `bird_species` (indexing → metadata → scoring → culling → keywords → bird_species).

## References

- [AGENTS.md](../../../AGENTS.md)
- [MCP_SEARCH_DISPATCH.md](../../../docs/technical/MCP_SEARCH_DISPATCH.md)
- [.agent/mcp_tools_reference.md](../../mcp_tools_reference.md)
- [workflows/safe_mcp_diagnostics.md](../../workflows/safe_mcp_diagnostics.md)
