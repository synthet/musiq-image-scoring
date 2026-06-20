---
type: Technical Reference
title: MCP search + dispatch contract
description: Compact search and dispatch workflow for is-be-mcp and is-ui-mcp, including sse_status and optional SSE proxy keys.
resource: docs/technical/MCP_SEARCH_DISPATCH.md
tags: [mcp, agents, api]
timestamp: 2026-06-20T00:00:00Z
okf_version: 0.1
---

# MCP search + dispatch contract

**Authority:** Action registry [`mcp/action_registry.json`](../../mcp/action_registry.json), overlay [`mcp/actions/overlay.yaml`](../../mcp/actions/overlay.yaml). Setup: [guides/setup/mcp-compact-servers.md](../guides/setup/mcp-compact-servers.md). Planning: [planning/mcp-search-dispatch.md](../planning/mcp-search-dispatch.md).

## Preferred agent entry point

| Server | Tools | Transport | Use |
|--------|-------|-----------|-----|
| **`is-be-mcp`** | **`search`**, **`dispatch`**, **`sse_status`** | Node stdio → Python worker | **Default backend** — always loads |
| **`is-be-live`** | **`search`**, **`dispatch`** | SSE when WebUI running | Optional direct attach; same registry |
| **`is-ui-mcp`** | **`search`**, **`dispatch`**, **`sse_status`** | Node stdio | **Default gallery** — always loads |
| **`is-ui-live`** | live IPC + CDP via dispatch | SSE when Electron running | Optional direct attach |

Set **`MCP_SSE_PROFILE=full`** on the WebUI process to restore the legacy ~54-tool SSE surface. Rename note: SSE key is **`is-be-live`** (formerly documented as `is-be-webui`); URL unchanged (`/mcp/sse` on port 7860).

Copy [`.cursor/mcp.example.json`](../../.cursor/mcp.example.json) → `.cursor/mcp.json`. Legacy profile stdio servers (`is-be-diag`, `is-be-jobs`, …) are **not** in the default config.

## Workflow

```text
1. sse_status()                         # optional: is-be-live / is-ui-live up?
2. search("why did scoring fail")       # on is-be-mcp
3. dispatch("diagnostics.get_error_summary", {})
4. dispatch("jobs.get_failed_images", {"limit": 20})
```

## `sse_status`

Read-only probe of the optional live SSE MCP endpoint.

```json
{
  "ok": true,
  "server": "is-be-live",
  "url": "http://127.0.0.1:7860/mcp/sse",
  "error": null
}
```

Gallery returns `"server": "is-ui-live"` and default URL `http://127.0.0.1:9373/mcp/sse` (or `gallery-mcp.lock`).

## `search`

```python
search(
    query: str,
    limit: int = 10,
    category: str | None = None,
    side_effect_level: str | None = None,
    read_only_only: bool = False,
    pipeline_area: str | None = None,
    include_schemas: bool = False,
    include_docs: bool = False,
    include_elevated: bool = False,
) -> dict
```

- Searches **action registry** only; never executes side effects.
- Returns `results[]` with `action_id`, `confidence`, `dispatch_hint`, `required_args`, `optional_args`.
- Sets `low_confidence: true` when top match is weak.

## `dispatch`

```python
dispatch(
    action_id: str,
    arguments: dict | None = None,
    dry_run: bool = False,
    confirmed: bool = False,
    request_id: str | None = None,
    allow_deprecated: bool = False,
    expected_version: int | None = None,
) -> dict
```

### Success envelope

```json
{
  "action_id": "diagnostics.get_error_summary",
  "action_version": 1,
  "request_id": "…",
  "status": "success",
  "side_effect_level": "read_only",
  "dry_run": false,
  "summary": "…",
  "data": {},
  "warnings": [],
  "errors": [],
  "artifacts": [],
  "logs_ref": null,
  "canonical_docs": ["docs/DIAGNOSTICS.md"]
}
```

### Error envelope

`status: "error"`, `code` (`unknown_action`, `validation_error`, `policy_rejected`, `confirmation_required`, `webui_unavailable`, `live_unavailable`, `playwright_unavailable`, `playwright_disabled`, …), `message`, `request_id`.

### Playwright proxy (live browser dispatch)

When Python validates a `handler_domain: playwright` action, it returns a delegate envelope instead of executing locally:

```json
{
  "status": "proxy",
  "code": "playwright_delegate",
  "action_id": "browser.navigate",
  "legacy_tool_name": "browser_navigate",
  "validated_args": { "url": "http://127.0.0.1:7860/ui/" },
  "request_id": "…"
}
```

Node **`is-be-mcp`** calls the Playwright MCP child with `legacy_tool_name` and wraps the result in a normal success envelope. Disable with `MCP_PLAYWRIGHT_ENABLED=0`.

## Dispatchable actions

### Read-only (PR1)

| action_id | Example arguments |
|-----------|-----------------|
| `diagnostics.run_doctor` | `{"no_gpu": true}` |
| `diagnostics.get_error_summary` | `{}` |
| `diagnostics.check_database_health` | `{}` |
| `diagnostics.validate_config` | `{}` |
| `diagnostics.get_database_engine_info` | `{}` |
| `diagnostics.verify_environment` | `{}` |
| `diagnostics.get_model_status` | `{}` |
| `logs.read_debug_log` | `{"lines": 100}` |
| `logs.get_server_log_tail` | `{"sources": "all", "lines": 100}` |
| `logs.search_logs` | `{"pattern": "error\|failed"}` |
| `config.get_config` | `{}` |
| `jobs.get_failed_images` | `{"limit": 20}` |
| `jobs.get_run_diagnostics` | `{"run_id": 123}` |
| `jobs.get_runner_status` | `{}` |
| `jobs.get_recent_jobs` | `{"limit": 10}` |
| `jobs.get_job_details` | `{"job_id": 123}` |
| `data.query_images` | `{"limit": 20, "folder_path": "…"}` |
| `data.get_image_details` | `{"file_path": "…"}` |
| `data.get_db_schema` | `{"table_name_prefix": "image"}` |
| `data.execute_sql` | `{"query": "SELECT …", "params": []}` |
| `data.get_embedding_stats` | `{}` |
| `diagnostics.diagnose_phase_consistency` | `{"image_id": 123}` (+ optional `folder_path`) |
| `diagnostics.get_stale_running_phase_status` | `{"min_age_seconds": 3600}` |
| `jobs.get_image_pipeline_failures` | `{"file_path": "…"}` or `{"image_id": 123}` |

### Side-effecting (confirmation required)

| action_id | Example arguments | Notes |
|-----------|-------------------|-------|
| `support.export_debug_bundle` | `{"confirmed": true}` via dispatch | Writes redacted zip; `output_path` optional (`.zip` only); returns metadata + `review_reminder` |

## Legacy tool mapping

| action_id | Legacy MCP tool | Domain server |
|-----------|-----------------|---------------|
| `diagnostics.get_error_summary` | `get_error_summary` | `is-be-diag` |
| `jobs.get_run_diagnostics` | `get_run_diagnostics` | `is-be-jobs` |
| `data.get_embedding_stats` | `get_embedding_stats` | `is-be-data` |

## Common agent workflows

Attach **`is-be-mcp`** or **`is-ui-mcp`**, then **`search`** → **`dispatch`**. If `low_confidence` is true, refine the query. For legacy raw tools not in the action registry, set **`MCP_SSE_PROFILE=full`** on WebUI.

### Scoring failure triage

```text
search("why did scoring fail")
dispatch("diagnostics.get_error_summary", {})
dispatch("jobs.get_failed_images", {"limit": 20})
dispatch("logs.search_logs", {"pattern": "error|failed"})
```

### System health

```text
dispatch("diagnostics.check_database_health", {})
dispatch("diagnostics.validate_config", {})
```

### Doctor (no GPU)

```text
dispatch("diagnostics.run_doctor", {"no_gpu": true})
```

### Export debug bundle (writes_files)

```text
search("export debug bundle")
dispatch("support.export_debug_bundle", {}, confirmed=True)
```

Review the zip before sharing. `secrets.json` is never included.

### `unknown_action` errors

Compact dispatch returns `code: unknown_action` with `details.suggestions`. **Do not** call raw legacy tool names from AGENTS.md unless they appear in the registry or you use full SSE profile.

Bare legacy names registered in the overlay (e.g. `execute_sql`) resolve automatically to `data.execute_sql`.

### Still unsupported via compact dispatch

`execute_code`, maintenance writes/jobs (`run_processing_job`, `prune_missing_files`, …), and other side-effecting actions unless listed above and in `ALLOWED_SIDE_EFFECT_ACTIONS`. Use **`MCP_SSE_PROFILE=full`** on WebUI for the full legacy tool surface (~54 tools).

## Gallery

Gallery **`is-ui-mcp`** uses the same **`search`** + **`dispatch`** + **`sse_status`** tools. Live CDP interaction actions (`live.cdp_click`, …) are documented in gallery [05-mcp-compact-servers.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/guides/05-mcp-compact-servers.md).

## Browser automation (Playwright via is-be-mcp)

No separate **`playwright`** MCP server — use **`browser.*`** actions on **`is-be-mcp`**. Registry: [`mcp/actions/playwright_registry.json`](../../mcp/actions/playwright_registry.json).

| action_id | Example arguments | Notes |
|-----------|-------------------|-------|
| `browser.navigate` | `{"url": "http://127.0.0.1:7860/ui/"}` | Open WebUI or any URL |
| `browser.snapshot` | `{}` | Accessibility tree (preferred over screenshot for agents) |
| `browser.click` | `{"target": "…"}` | Requires snapshot ref or selector |
| `browser.take_screenshot` | `{}` | PNG capture |
| `browser.wait_for` | `{"text": "…"}` or selector fields per schema | Wait for page state |
| `browser.run_code_unsafe` | `{"code": "async (page) => …"}` | **`confirmed=True`** required; RCE-equivalent |

```text
search("browser snapshot webui")
dispatch("browser.navigate", {"url": "http://127.0.0.1:7860/ui/"}, dry_run=true)
dispatch("browser.snapshot", {})
```

## Vocabulary (do not use)

Use **`is-be-*`** and **`is-ui-*`** keys only; remove legacy MCP server names from user configs. Prefer compact **`search`/`dispatch`** over attaching many profile servers.
