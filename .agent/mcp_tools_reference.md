# MCP Tools Quick Reference for AI Agents

This document tracks the tools registered in [`modules/mcp_server.py`](../modules/mcp_server.py) (**46** tools).

## Connection modes

- **`imgscore-py-stdio`**: **Python workspace** — stdio; `cwd` / `PYTHONPATH` = `${workspaceFolder}` (this repo).
- **`imgscore-el-stdio`**: **Electron workspace** — stdio; `cwd` / `PYTHONPATH` = path to sibling **image-scoring** checkout.
- **`imgscore-py-sse`** / **`imgscore-el-sse`**: SSE to WebUI (same URL; pick the key for your workspace). Default `http://127.0.0.1:7860/mcp/sse` (confirm with `GET /mcp-status` → `expected_sse_url`).
- **`execute_code`**: requires SSE **and** `ENABLE_MCP_EXECUTE_CODE=1` on the WebUI process.

## Tool index (by category)

### Diagnostic & environment

| Tool | Description |
|------|-------------|
| **`get_error_summary`** | Failed jobs, missing scores, orphans |
| **`check_database_health`** | Integrity issues (orphans, duplicates, …) |
| **`get_model_status`** | GPU / CUDA / model load |
| **`diagnose_phase_consistency`** | `image_id` (+ optional `folder_path`): folder vs image phase mismatch |
| **`get_stale_running_phase_status`** | Long-`running` `image_phase_status` rows (`min_age_seconds`, `limit`) |
| **`get_migration_parity`** | Firebird↔Postgres parity snapshot (when configured) |
| **`verify_environment`** | Host / venv / key deps sanity check |

### Data query

| Tool | Description |
|------|-------------|
| **`get_database_stats`** | Aggregate stats |
| **`query_images`** | Filters, sort, pagination |
| **`get_image_details`** | By `file_path` |
| **`search_images_by_hash`** | By `image_hash` |
| **`execute_sql`** | `SELECT` only |

### Errors, paths, files

| Tool | Description |
|------|-------------|
| **`get_failed_images`** | Missing key scores (`limit` default 50) |
| **`get_incomplete_images`** | Broader incomplete rows (`limit` default 100) |
| **`validate_file_paths`** | Filesystem check (`limit` default 100) |
| **`summarize_directory`** | File counts / sizes under a folder path |
| **`search_missing_sidecars`** | NEF without matching XMP in a directory |

### Jobs, runs, performance

| Tool | Description |
|------|-------------|
| **`get_recent_jobs`** | History (`limit` default 10) |
| **`get_job_details`** | One job by `job_id` (= `jobs.id`, same as API workflow `run_id`); payload + log tail |
| **`get_job_phases`** | Phase rows for a job |
| **`get_job_stage_images`** | Per-image phase status for a job+`phase_code`; optional `include_steps` |
| **`get_run_diagnostics`** | `post_run_audit` from queue_payload + per-phase `image_phase_status` counts for `run_id` |
| **`get_performance_metrics`** | Recent job stats (`days` default 7) |
| **`get_runner_status`** | Runner progress/logs |
| **`get_pipeline_stats`** | Runners + dispatcher + queue sizes |
| **`run_processing_job`** | `job_type`: scoring \| tagging \| clustering; `input_path`; optional `args` |

### HTTP, DB engine, embeddings, stacks

| Tool | Description |
|------|-------------|
| **`probe_backend_http`** | GET a relative path on the WebUI base URL (e.g. `/api/scope/tree`); timing + body preview |
| **`get_database_engine_info`** | `database.engine`, connector type, safe targets, DB ping |
| **`get_embedding_stats`** | Counts with/without `image_embedding`; optional `folder_path` |
| **`check_stack_invariants`** | Singleton stacks, orphan `stack_id`, empty stacks (+ samples) |

### Config & logs

| Tool | Description |
|------|-------------|
| **`validate_config`** | Structural checks (`ok`, `issues`, `warnings`); adds `database_reachable` when DB init succeeded |
| **`get_config`** | Full config dict |
| **`set_config_value`** | Dot-key update |
| **`read_debug_log`** | `lines` default 100; JSON lines from `debug.log` |
| **`get_server_log_tail`** | `sources` default `all` (`all` \| `webui` \| `debug`); `lines` default 100 — same tails as `GET /api/status/log-tails` |

### Folders, stacks, similarity, gallery

| Tool | Description |
|------|-------------|
| **`get_folder_tree`** | Optional `root_path` |
| **`get_stacks_summary`** | Optional `folder_path` |
| **`get_gallery_status`** | Gradio/React gallery wiring when WebUI exposes it |
| **`search_similar_images`** | `example_path` or `example_image_id` |
| **`find_near_duplicates`** | Optional `threshold`, `folder_path`, `limit` |
| **`propagate_tags`** | Keyword propagation (`dry_run` default true) |
| **`find_outliers`** | Embedding outlier analysis |

### Maintenance (writes)

| Tool | Description |
|------|-------------|
| **`rebase_file_paths`** | Batch path prefix update (`dry_run` default true) |
| **`set_image_metadata`** | Rating/label for a `file_path` |
| **`prune_missing_files`** | Remove DB rows for missing files (`dry_run` default true) |

### Execute code (SSE + opt-in)

| Tool | Description |
|------|-------------|
| **`execute_code`** | Python in WebUI; SSE + `ENABLE_MCP_EXECUTE_CODE=1`; assign `result` to return |

## Common workflows

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

### Slow HTTP / scope tree
```
probe_backend_http("/api/scope/tree", timeout_ms) → read_debug_log
```

### Run / workflow debugging
```
get_recent_jobs → get_job_details(job_id) → get_job_phases → get_job_stage_images
```

### Data quality
```
get_database_stats → check_database_health → get_incomplete_images → validate_file_paths
```

## Important notes

- Most tools need a working DB (`prepare_mcp_embedded` / `db.init_db`).  
- **`get_model_status`**, **`probe_backend_http`**, **`get_database_engine_info`**, **`verify_environment`** do not require DB for their primary output (DB-dependent fields may be partial).  
- **`validate_config`** structural checks work without DB; MCP adds DB reachability when available.  
- **`execute_sql`**: SELECT only; dangerous patterns blocked.  
- **`validate_file_paths`** / **`get_incomplete_images`** can be heavy — use `limit`.  

## Quick decision tree

- **"Why did scoring fail?"** → `get_error_summary` → `get_failed_images` → `get_model_status` → `read_debug_log`  
- **"Is the system healthy?"** → `check_database_health` → `get_model_status` → `validate_config`  
- **"How fast is processing?"** → `get_performance_metrics` → `get_runner_status` → `get_pipeline_stats`  
- **"Find images with X"** → `query_images` → `get_image_details`  
- **"What's in the database?"** → `get_database_stats` → `get_folder_tree` → `get_stacks_summary`  
- **"Why is this run stuck?"** → `get_job_details` → `get_job_phases` → `get_job_stage_images`  
