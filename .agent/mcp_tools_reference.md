# MCP Tools Quick Reference for AI Agents

This document tracks the tools registered in [`modules/mcp_server.py`](../modules/mcp_server.py). **Tool count** matches `@mcp.tool` registrations in that file (regenerate the numbered inventory in [`AGENTS.md`](../AGENTS.md) with `python scripts/generate_mcp_tool_inventory.py --update-docs AGENTS.md docs/technical/MCP_DEBUGGING_TOOLS.md`). For **safe vs high-risk** tools, see [workflows/safe_mcp_diagnostics.md](workflows/safe_mcp_diagnostics.md).

## Connection modes

- **`image-scoring-backend-stdio`**, **`image-scoring-backend-webui`**, **`image-scoring-backend-postgres`**: backend [`.cursor/mcp.json`](../.cursor/mcp.json)
- **`image-scoring-gallery-stdio`**, **`image-scoring-gallery-live`**: gallery `.cursor/mcp.json`
- **`execute_code`**: requires **`image-scoring-backend-webui`** and `ENABLE_MCP_EXECUTE_CODE=1` on the WebUI process.

## Postgres query patterns (operators)

Canonical mappings (avoid legacy names):

- `jobs.input_path` (not `jobs.folder_path`)
- `image_phase_status.phase_id` + join `pipeline_phases.code` (not `image_phase_status.phase_code`)
- `job_image_actions.action` (not `image_phase_status.action`)
- `pipeline_phases` (not `phases`)

Copy/paste-ready queries:

```sql
-- 1) Recent jobs (latest first)
SELECT
  j.id,
  j.job_type,
  j.status,
  j.input_path,
  j.created_at,
  j.started_at,
  j.completed_at
FROM jobs j
ORDER BY j.created_at DESC
LIMIT 20;
```

```sql
-- 2) Recent jobs with duration (seconds)
SELECT
  j.id,
  j.job_type,
  j.status,
  j.input_path,
  j.created_at,
  j.completed_at,
  ROUND(EXTRACT(EPOCH FROM (j.completed_at - j.created_at))::numeric, 2) AS duration_s
FROM jobs j
WHERE j.created_at >= NOW() - INTERVAL '7 days'
ORDER BY j.created_at DESC
LIMIT 50;
```

```sql
-- 3) Phase counts for one job (by canonical phase code)
SELECT
  p.code AS phase_code,
  ips.status,
  COUNT(*) AS row_count
FROM image_phase_status ips
JOIN pipeline_phases p ON p.id = ips.phase_id
WHERE ips.job_id = $1
GROUP BY p.code, ips.status
ORDER BY p.code, ips.status;
```

```sql
-- 4) Per-image stage rows for one job + phase
SELECT
  ips.job_id,
  ips.image_id,
  p.code AS phase_code,
  ips.status,
  ips.started_at,
  ips.updated_at,
  ips.error_message
FROM image_phase_status ips
JOIN pipeline_phases p ON p.id = ips.phase_id
WHERE ips.job_id = $1
  AND p.code = $2
ORDER BY ips.image_id, ips.updated_at DESC;
```

```sql
-- 5) Action aggregation for one job
SELECT
  jia.action,
  COUNT(*) AS action_count
FROM job_image_actions jia
WHERE jia.job_id = $1
GROUP BY jia.action
ORDER BY action_count DESC, jia.action;
```

```sql
-- 6) Action aggregation by phase (join via image_phase_status + pipeline_phases)
SELECT
  p.code AS phase_code,
  jia.action,
  COUNT(*) AS action_count
FROM job_image_actions jia
JOIN image_phase_status ips
  ON ips.job_id = jia.job_id
 AND ips.image_id = jia.image_id
JOIN pipeline_phases p ON p.id = ips.phase_id
WHERE jia.job_id = $1
GROUP BY p.code, jia.action
ORDER BY p.code, action_count DESC, jia.action;
```

## Tool index (by category)

### Diagnostic & environment

| Tool | Description |
|------|-------------|
| **`get_error_summary`** | Failed jobs, missing scores, orphans, `stale_running_count` |
| **`check_database_health`** | Integrity issues (orphans, duplicates, …) |
| **`get_model_status`** | GPU / CUDA / model load |
| **`diagnose_phase_consistency`** | `image_id` (+ optional `folder_path`): folder vs image phase mismatch |
| **`get_stale_running_phase_status`** | Long-`running` `image_phase_status` rows (`min_age_seconds`, `limit`) |
| **`verify_environment`** | Host / venv / key deps sanity check |
| **`get_system_resources`** | CPU / RAM / optional `nvidia-smi` snapshot |

### Data query

| Tool | Description |
|------|-------------|
| **`get_database_stats`** | Aggregate stats |
| **`query_images`** | Filters, sort, pagination |
| **`get_image_details`** | By `file_path` |
| **`search_images_by_hash`** | By `image_hash` |
| **`get_db_schema`** | PostgreSQL `information_schema` columns (optional `table_name_prefix`) |
| **`execute_sql`** | Read-only `SELECT` / `WITH … SELECT` (`?` placeholders); pair with **`get_db_schema`** |

### Errors, paths, files

| Tool | Description |
|------|-------------|
| **`get_failed_images`** | Missing key scores (`limit` default 50, `offset` optional) |
| **`get_incomplete_images`** | Broader incomplete rows (`limit` default 100) |
| **`validate_file_paths`** | Filesystem check; optional `folder_path`, `missing_only` |

### Jobs, runs, performance

| Tool | Description |
|------|-------------|
| **`get_recent_jobs`** | History (`limit` default 10) |
| **`get_job_details`** | One job by `job_id` (= `jobs.id`, same as API workflow `run_id`); payload + log tail |
| **`get_job_phases`** | Phase rows for a job |
| **`get_job_stage_images`** | Per-image phase status for a job+`phase_code`; optional `include_steps` |
| **`get_run_diagnostics`** | `post_run_audit` from queue_payload + per-phase `image_phase_status` counts for `run_id` |
| **`get_job_execution_report`** | `report_json` + paginated `job_image_actions` + `summary.action_counts` |
| **`get_image_pipeline_failures`** | `job_image_actions` with `failed` for one image (`image_id` or `file_path`) |
| **`get_location_stats`** | GPS / geocode coverage on `image_exif` |
| **`export_debug_bundle`** | Redacted zip (config, env, doctor, log tails); optional `output_path` ending in `.zip` |
| **`get_performance_metrics`** | Recent job stats (`days` default 7) |
| **`get_runner_status`** | Runner progress/logs |
| **`get_pipeline_stats`** | Runners + dispatcher + queue sizes |
| **`run_processing_job`** | `job_type`: scoring \| tagging \| clustering \| bird_species; creates `jobs` row; returns integer `job_id` / `jobs_id` |
| **`manage_runners`** | `stop` \| `status` on in-process runners (WebUI); not for starting jobs |

### DB engine, embeddings, stacks

| Tool | Description |
|------|-------------|
| **`get_database_engine_info`** | `database.engine`, connector type, safe targets, DB ping |
| **`get_embedding_stats`** | Counts with/without `image_embedding`; optional `folder_path` |
| **`check_stack_invariants`** | Singleton stacks, orphan `stack_id`, empty stacks (+ samples) |

### Config & logs

| Tool | Description |
|------|-------------|
| **`validate_config`** | Structural checks (`ok`, `issues`, `warnings`); adds `database_reachable` when DB init succeeded |
| **`get_config`** | Config dict with sensitive keys redacted |
| **`set_config_value`** | Dot-key update |
| **`read_debug_log`** | `lines` default 100; JSON lines from `debug.log` |
| **`get_server_log_tail`** | `sources` default `all` (`all` \| `webui` \| `debug`); `lines` default 100 — same tails as `GET /api/status/log-tails` |
| **`search_logs`** | Regex over recent log tails (`pattern`, `sources`, `context_lines`, …) |

### Folders, stacks, similarity

| Tool | Description |
|------|-------------|
| **`get_folder_tree`** | Optional `root_path` |
| **`get_stacks_summary`** | Optional `folder_path` |
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

### HTTP / scope issues
```
search_logs("scope|/api/scope", sources="webui") → read_debug_log
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
- **`get_model_status`**, **`get_database_engine_info`**, **`verify_environment`**, **`get_system_resources`**, **`search_logs`** do not require DB for their primary output (DB-dependent fields may be partial).  
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
