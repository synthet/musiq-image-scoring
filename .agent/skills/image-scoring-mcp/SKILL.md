---
name: image-scoring-mcp
description: Vexlum Scoring MCP server tools — diagnostics, queries, monitoring, debugging workflows, and execute_code with Gradio access.
---

# Vexlum Scoring MCP server

The project includes a Model Context Protocol (MCP) server whose tools are registered in [`modules/mcp_server.py`](../../../modules/mcp_server.py) (`@mcp.tool` count is authoritative for the checkout). Full index: [`mcp_tools_reference.md`](../../mcp_tools_reference.md). **Safe triage:** [workflows/safe_mcp_diagnostics.md](../../workflows/safe_mcp_diagnostics.md).

## Configuration

- **`imgscore-py-stdio`**: **Python** Cursor workspace — stdio; `cwd` + `PYTHONPATH` = this repo root.
- **`imgscore-el-stdio`**: **Electron** Cursor workspace — stdio; `cwd` + `PYTHONPATH` = sibling **image-scoring** path.
- **`imgscore-py-sse`** / **`imgscore-el-sse`**: WebUI SSE (same URL); `execute_code` when `ENABLE_MCP_EXECUTE_CODE=1`.
- **`execute_code`**: SSE only; set **`ENABLE_MCP_EXECUTE_CODE=1`** on the WebUI process.

## MCP Schema Checks

**Before calling any MCP tool**, check the tool schema/descriptor for required parameters and types.

- **Required parameters**: Check the `required` array in the schema.
- **Parameter types**: Verify `properties.<name>.type`.
- **Optional parameters**: Use when they improve results (e.g. `limit`, `folder_path`).

Tool descriptors can be found in the `mcps/` folder or via `list_tools` on the server.

## Tool index (abbrev.)

| Area | Tools |
|------|--------|
| Diagnostic | `get_error_summary`, `check_database_health`, `get_model_status`, `diagnose_phase_consistency`, `get_stale_running_phase_status`, `verify_environment`, `get_system_resources` |
| Query | `get_database_stats`, `query_images`, `get_image_details`, `search_images_by_hash`, `get_db_schema`, `execute_sql` |
| Errors & Paths | `get_failed_images`, `get_incomplete_images`, `validate_file_paths` |
| Performance & Jobs | `get_performance_metrics`, `get_runner_status`, `get_recent_jobs`, `get_job_details`, `get_job_phases`, `get_job_stage_images`, `get_run_diagnostics`, `get_job_execution_report`, `get_image_pipeline_failures`, `get_location_stats`, `export_debug_bundle`, `get_pipeline_stats`, `run_processing_job`, `manage_runners` |
| Engine & stacks | `get_database_engine_info`, `get_embedding_stats`, `check_stack_invariants` |
| Config & Logs | `validate_config`, `get_config`, `set_config_value`, `read_debug_log`, `get_server_log_tail`, `search_logs` |
| Folders & Stacks | `get_folder_tree`, `get_stacks_summary`, `search_similar_images`, `find_near_duplicates`, `propagate_tags`, `find_outliers` |
| Execute Code | `execute_code` (SSE + env flag) |

## Workflows

### Scoring failures
```
get_error_summary → get_failed_images → get_model_status → read_debug_log
```

### System health
```
check_database_health → get_model_status → validate_config → validate_file_paths
```

### Performance
```
get_performance_metrics → get_recent_jobs → get_pipeline_stats → get_runner_status
```

### Data quality
```
get_database_stats → check_database_health → get_incomplete_images → validate_file_paths
```

## Notes

- Most tools require DB access; `get_model_status` does not. `validate_config` does structural checks without DB; MCP adds `database_reachable` when DB init succeeded.
- `execute_sql` is SELECT-only.
- `validate_file_paths` / `get_incomplete_images` — use `limit` on large libraries.
