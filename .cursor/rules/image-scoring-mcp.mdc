---
description: Use image-scoring MCP tools for app-level diagnostics, job monitoring, and Gradio debugging
alwaysApply: true
---

# Vexlum Scoring MCP

When the user asks about **debugging**, **investigating failures**, **database health**, **scoring/tagging/clustering jobs** (batch rows in `jobs`), or **Gradio / WebUI state**, use the image-scoring MCP servers.

## Naming (`is-` = image scoring)

| Prefix | Repo | Default keys |
|--------|------|--------------|
| **`is-be-*`** | backend | **`is-be-mcp`**, optional **`is-be-live`** |
| **`is-ui-*`** | gallery | **`is-ui-mcp`**, optional **`is-ui-live`** |

User `~/.cursor/mcp.json`: **`github`**, **`subagent-orchestrator`**, etc. — **not** `is-be-*` / `is-ui-*`. Project keys: copy **`mcp.example.json`** → **`.cursor/mcp.json`** in each repo.

## Compact dispatch (default)

**`is-be-mcp`** and **`is-be-live`** (default compact SSE) expose only **`search`** and **`dispatch`** — not raw tool names from AGENTS.md. Workflow: **`search(query)`** → **`dispatch(action_id, arguments)`** using registry `action_id` values (`category.tool`). On **`unknown_action`**, read `details.suggestions`; use `search(..., include_schemas=True)` before dispatch when unsure. Contract: [docs/technical/MCP_SEARCH_DISPATCH.md](../../docs/technical/MCP_SEARCH_DISPATCH.md); skill: `.cursor/skills/image-scoring-mcp/SKILL.md`.

Gallery: **`is-ui-mcp`** → same **`search`** / **`dispatch`** over gallery actions (`mcp-server/action_registry.json`).

## Backend server keys (default config)

| Server key | Transport | When to use |
|------------|-----------|-------------|
| **`is-be-mcp`** | stdio | **Default** — `search`, `dispatch` |
| **`is-be-live`** | SSE | **Default compact** — same `search`, `dispatch` as `is-be-mcp`; **`MCP_SSE_PROFILE=full`** for legacy tools + `execute_code` |

## Gallery server keys (sibling repo)

| Server key | When to use |
|------------|-------------|
| **`is-ui-mcp`** | **Default** — `search`, `dispatch` over gallery actions |
| **`is-ui-live`** | SSE: live IPC + CDP actions via dispatch when Electron dev is running |

Not in default gallery config: **`is-ui-router`**, **`is-ui-local`**, **`is-ui-api`** (debug entrypoints only).

## Terminology (agents)

**Canonical reference:** [`docs/technical/PIPELINE_TERMINOLOGY.md`](../../docs/technical/PIPELINE_TERMINOLOGY.md).

- **Pipeline stages (user-facing):** Discovery → Inspection → **Quality Analysis** → **Similarity Clustering** → **Tagging**
- **DB `phase_code` values:** `indexing`, `metadata`, `scoring`, `culling`, `keywords`
- **Runs:** UI says **run**; MCP/API still use `job_id` / `get_recent_jobs`

**Before calling**: Check tool schema in `mcps/<server>/tools/<tool>.json`.

## Quick decision tree

- **Unknown which action?** → **`search`** on **`is-be-mcp`**
- **Why did scoring fail?** → `dispatch("diagnostics.get_error_summary", {})` → `dispatch("jobs.get_failed_images", {"limit": 20})` (missing scores; not per-job trace)
- **Why did one image fail in a job?** → `dispatch("jobs.get_image_pipeline_failures", {"file_path": "…"})`
- **Custom SQL** → `dispatch("data.get_db_schema", {})` then `dispatch("data.execute_sql", {"query": "SELECT …"})`
- **Is the system healthy?** → `dispatch("diagnostics.check_database_health", {})`, `dispatch("diagnostics.validate_config", {})`
- **Redacted support bundle** → `dispatch("support.export_debug_bundle", {}, confirmed=True)`
- **Legacy tools not in registry** → backend WebUI with **`MCP_SSE_PROFILE=full`**
- **Gallery won't start / IPC** → **`dispatch("local.gallery_status", {})`** on **`is-ui-mcp`**; live CDP via **`is-ui-live`** dispatch
- **Gradio in-process debug** → **`is-be-live`** + `execute_code` (`ENABLE_MCP_EXECUTE_CODE=1`)

## High-risk tools (SSE / maintenance profile only)

`execute_code`, `set_config_value`, `run_processing_job`, `process_newly_imported_folders`, `rebase_file_paths`, `prune_missing_files`, `set_image_metadata`, `propagate_tags`, `manage_runners`.

**SSE:** **`is-be-live`** attaches to the live WebUI; `execute_code` runs in that process when enabled.

## Full tool inventory

Regenerate from [`modules/mcp_server.py`](../../modules/mcp_server.py): `python scripts/generate_mcp_tool_inventory.py --update-docs AGENTS.md docs/technical/MCP_DEBUGGING_TOOLS.md --update-catalog`. See [`.agent/mcp_tools_reference.md`](../../.agent/mcp_tools_reference.md), [`.agent/workflows/safe_mcp_diagnostics.md`](../../.agent/workflows/safe_mcp_diagnostics.md).
