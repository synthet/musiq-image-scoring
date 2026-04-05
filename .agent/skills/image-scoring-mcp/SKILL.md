---
name: image-scoring-mcp
description: Image Scoring MCP server tools — diagnostics, queries, monitoring, debugging workflows, and execute_code with Gradio access.
---

# Image Scoring MCP Server

The project includes a Model Context Protocol (MCP) server that exposes **44** diagnostic and query tools. Implementation: [`modules/mcp_server.py`](../../../modules/mcp_server.py). Full index: [`mcp_tools_reference.md`](../../mcp_tools_reference.md).

## Configuration

- **`imgscore-py-stdio`**: **Python** Cursor workspace — stdio; `cwd` + `PYTHONPATH` = this repo root.
- **`imgscore-el-stdio`**: **Electron** Cursor workspace — stdio; `cwd` + `PYTHONPATH` = sibling **image-scoring** path.
- **`imgscore-py-sse`** / **`imgscore-el-sse`**: WebUI SSE (same URL); `execute_code` when `ENABLE_MCP_EXECUTE_CODE=1`.
- **`execute_code`**: SSE only; set **`ENABLE_MCP_EXECUTE_CODE=1`** on the WebUI process.

## Tool index (abbrev.)

| Area | Tools |
|------|--------|
| Diagnostic | `get_error_summary`, `check_database_health`, `get_model_status`, `diagnose_phase_consistency` |
| Query | `get_database_stats`, `query_images`, `get_image_details`, `search_images_by_hash`, `execute_sql` |
| Errors / paths | `get_failed_images`, `get_incomplete_images`, `validate_file_paths` |
| Jobs | `get_performance_metrics`, `get_runner_status`, `get_recent_jobs`, `get_pipeline_stats`, `run_processing_job` |
| Config | `validate_config`, `get_config`, `set_config_value`, `read_debug_log` |
| Stacks / similarity | `get_folder_tree`, `get_stacks_summary`, `search_similar_images`, `find_near_duplicates`, `propagate_tags`, `find_outliers` |
| Gradio | `execute_code` (SSE + env flag) |

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
