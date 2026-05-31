---
description: Safe MCP diagnostics — prefer read-only tools and schema checks
---

## Purpose

Use **Vexlum Scoring MCP** without accidental writes, config mutation, or unsafe `execute_code`.

## When to use

- Any AI or operator is connecting **`scoring`** or **`webui`** MCP to a live WebUI.

## Canonical docs first

- [AGENTS.md](../../AGENTS.md) — full tool list
- [.cursor/rules/mcp-schema-check.mdc](../../.cursor/rules/mcp-schema-check.mdc)
- [.cursor/rules/image-scoring-mcp.mdc](../../.cursor/rules/image-scoring-mcp.mdc)
- `mcps/project-0-image-scoring-image-scoring/tools/*.json`

## Recommended read-first / read-only triage

Prefer, in roughly this order:

- `validate_config`, `verify_environment`, `get_database_engine_info`
- `check_database_health`, `get_error_summary`
- `get_failed_images`, `get_incomplete_images` (with limits)
- `get_db_schema`, `execute_sql` (SELECT-only; enforced server-side)
- `get_job_details`, `get_job_phases`, `get_run_diagnostics`, `get_job_execution_report`, `get_image_pipeline_failures`
- `search_logs`, `get_server_log_tail`, `read_debug_log`
- `export_debug_bundle` (review zip before sharing — still a write to local disk)

## High-risk tools (disable by default in user MCP `disabledTools` when possible)

Only enable when the user explicitly wants automation or mutation:

- `execute_code` — runs in WebUI process (SSE + `ENABLE_MCP_EXECUTE_CODE=1`)
- `set_config_value` — persists config
- `run_processing_job` — starts processing
- `process_newly_imported_folders` — may start jobs
- `rebase_file_paths` — mass path rewrites
- `prune_missing_files` — destructive DB cleanup
- `set_image_metadata` — writes rating/label
- `propagate_tags` — keyword propagation
- `manage_runners` — stop/status side effects on runners

Exact names must match [AGENTS.md](../../AGENTS.md) tool inventory (regenerate from `modules/mcp_server.py` via `scripts/generate_mcp_tool_inventory.py` when needed).

## Shared host / SSE warnings

- **SSE** (**`webui`**) connects to a **live** WebUI process on `127.0.0.1:7860` (or configured port). Others on the same machine could theoretically use the same endpoint — treat as sensitive when `execute_code` is enabled.

## Do not

- Do not call write/maintenance tools “to see what happens.”
- Do not skip reading JSON schemas for tools with complex parameters.
