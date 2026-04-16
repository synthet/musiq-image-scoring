# MCP Debugging Tools for Cursor

This document describes the MCP (Model Context Protocol) server integration that provides remote debugging tools for Cursor IDE.

## Overview

The MCP server exposes a comprehensive set of debugging tools that allow Cursor IDE (and AI agents) to interact with the Image Scoring application:
- **Database Operations**: Query and analyze the Firebird database, check data integrity
- **Job Monitoring**: Monitor scoring/tagging job progress and history
- **Error Diagnostics**: Identify failed images, error patterns, and system issues
- **Performance Analysis**: Track processing metrics and throughput
- **System Diagnostics**: Check GPU/model status, validate configuration
- **File Validation**: Verify file paths and data consistency
- **Log Access**: Read debug logs and investigate issues
- **Configuration Management**: Read and update application settings

## Installation

1. Install the MCP SDK:
```bash
pip install mcp
```

2. Configure Cursor to use the MCP server (see Configuration section below)

## Configuration

### SSE URL and port

The WebUI serves MCP at **`/mcp/sse`**. Default URL is `http://127.0.0.1:7860/mcp/sse` if the app listens on port 7860. If your port differs, open **`GET /mcp-status`** on the WebUI and use **`expected_sse_url`**.

### Option 1: Cursor Settings (Recommended)

Add the following to your Cursor MCP settings (Settings → MCP → Add Server):

```json
{
  "name": "imgscore-py-stdio",
  "command": "python",
  "args": ["-m", "modules.mcp_server"],
  "cwd": "${workspaceFolder}",
  "env": { "PYTHONPATH": "${workspaceFolder}" }
}
```

When the Cursor workspace is **image-scoring-gallery**, use the same `command` / `args` but name the server **`imgscore-el-stdio`** and set `cwd` / `PYTHONPATH` to your **image-scoring-backend** checkout path. For WebUI / `execute_code`, register **`imgscore-el-sse`** (or **`imgscore-py-sse`** in the Python workspace) with the `url` from `GET /mcp-status`.

### Option 2: Project Config File

Copy the `mcp_config.json` from the project root to your Cursor config directory:
- Windows: `%APPDATA%\Cursor\User\globalStorage\cursor.mcp\mcp.json`
- Or merge its contents into your existing MCP configuration

### Option 3: Running with WebUI

Set the environment variable to enable MCP alongside the WebUI:

```bash
# Windows PowerShell
$env:ENABLE_MCP_SERVER = "1"
python webui.py

# Linux/WSL
ENABLE_MCP_SERVER=1 python webui.py
```

## Available Tools

## Postgres query patterns (operators)

Use these canonical column/table mappings when writing ad-hoc SQL against Postgres:

- `jobs.input_path` (not `jobs.folder_path`)
- `image_phase_status.phase_id` joined to `pipeline_phases.code` (not `image_phase_status.phase_code`)
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

### Firebird Admin Tools (New)
*Requires `firebird-admin` MCP server.*

#### `list_tables`
List all user tables in the database (excludes system tables).

#### `get_table_schema`
Get detailed schema information for a specific table.

**Parameters:**
- `table_name` - Name of the table

#### `run_sql`
Execute raw SQL queries. 
**WARNING**: Supports both READ and WRITE operations. Use with caution.

**Parameters:**
- `query` - SQL query string
- `params` - Optional list of parameters

#### `get_firebird_version`
Get the Firebird database engine version.

### Database Tools (Standard)

#### `get_database_stats`
Get comprehensive database statistics including:
- Total image count
- Distribution by rating and label
- Score distribution histogram
- Average scores per model
- Folder and stack counts
- Today's activity

**Example Output:**
```json
{
  "total_images": 15234,
  "by_rating": {"0": 5000, "1": 100, "2": 500, "3": 3000, "4": 5000, "5": 1634},
  "average_scores": {"general": 0.68, "technical": 0.72, "aesthetic": 0.65}
}
```

#### `query_images`
Query images with flexible filtering:
- `limit` / `offset` - Pagination
- `sort_by` - Sort column (created_at, score_general, etc.)
- `order` - asc/desc
- `min_score` / `max_score` - Score range filter
- `rating` - Filter by rating (0-5)
- `label` - Filter by color label
- `keyword` - Keyword search
- `folder_path` - Filter by folder

**Example:**
```
query_images(limit=10, min_score=0.8, sort_by="score_general", order="desc")
```

#### `get_image_details`
Get full details for a specific image by file path.

**Parameters:**
- `file_path` - Full path to the image

#### `execute_sql`
Execute a read-only SQL SELECT query. Only SELECT queries are allowed for safety.

**Parameters:**
- `query` - SQL SELECT statement
- `params` - Optional query parameters

**Example:**
```sql
SELECT file_name, score_general, rating 
FROM images 
WHERE score_general > 0.8 
ORDER BY score_general DESC 
LIMIT 10
```

#### `search_images_by_hash`
Search for an image by its SHA256 content hash.

**Parameters:**
- `image_hash` - SHA256 hash of image content

#### `search_similar_images`
Find images visually similar to an example image using stored MobileNetV2 embeddings and cosine similarity. Embeddings are persisted to the database during clustering; if the example image has no stored embedding it is computed on the fly and saved.

**Parameters:**
- `example_path` (string, optional) - File path of the example image
- `example_image_id` (integer, optional) - Database ID of the example image (alternative to example_path)
- `limit` (integer, default 20) - Maximum number of results
- `folder_path` (string, optional) - Restrict search to images in this folder
- `min_similarity` (number, optional) - Minimum cosine similarity threshold (0-1)

**Returns:** List of `{ image_id, file_path, similarity }` sorted by descending similarity. Requires at least one of `example_path` or `example_image_id`.

### Job & Runner Tools

#### `get_recent_jobs`
Get recent scoring/tagging jobs with status.

**Parameters:**
- `limit` - Number of jobs to return (default: 10)

#### `get_runner_status`
Get current status of background runners including:
- Whether scoring/tagging is running
- Progress (current/total)
- Recent log output

### Configuration Tools

#### `get_config`
Get current application configuration from config.json.

#### `set_config_value`
Set a configuration value.

**Parameters:**
- `key` - Configuration key
- `value` - Value to set (any JSON-compatible type)

### Analysis Tools

#### `get_folder_tree`
Get folder tree structure with image counts per folder.

**Parameters:**
- `root_path` - Optional root path to filter

#### `get_incomplete_images`
Get images with missing or incomplete data (composite scores, model scores, ratings, labels).

**Parameters:**
- `limit` - Max results (default: 100)

#### `get_stacks_summary`
Get summary of image stacks/clusters including:
- Total stacks
- Size distribution
- Largest stacks
- Unstacked image count

**Parameters:**
- `folder_path` - Optional folder filter

#### `read_debug_log`
Read recent entries from the debug log file.

**Parameters:**
- `lines` - Number of lines to read (default: 100)

### Debugging & Diagnostics Tools

#### `get_failed_images`
Get images that failed processing or have missing scores. Identifies which specific scores are missing.

**Parameters:**
- `limit` - Max number of results (default: 50)

**Returns:** List of images with missing scores, including which scores (general, technical, spaq, koniq) are missing.

**Use Case:** Find problematic images that need reprocessing or identify patterns in failures.

#### `get_error_summary`
Get comprehensive summary of errors and issues in the database.

**Returns:**
- Failed jobs count
- Images missing various scores (general, technical, spaq, koniq, ava, paq2piq, liqe)
- Orphaned images (no folder)
- Images with empty paths
- Recent failed jobs with error messages

**Use Case:** Quick health check to identify systemic issues or data quality problems.

#### `check_database_health`
Check database for inconsistencies, orphaned records, and data integrity issues.

**Returns:**
- Status: "healthy", "unhealthy", or "error"
- List of issues (critical problems)
- List of warnings (non-critical issues)
- Summary counts

**Checks:**
- Orphaned images (invalid folder_id)
- Orphaned stack references (invalid stack_id)
- Duplicate file paths
- Images with hash but no path
- Empty folders/stacks

**Use Case:** Validate data integrity before major operations or after migrations.

#### `validate_file_paths`
Validate that file paths in database actually exist on the filesystem.

**Parameters:**
- `limit` - Max number of paths to check (default: 100)

**Returns:**
- Number checked, exists, missing
- List of missing files with IDs

**Use Case:** Find images that were moved or deleted, identify broken references.

#### `get_performance_metrics`
Get performance metrics from recent jobs.

**Returns:**
- Average job duration (seconds)
- Images processed per hour
- Total images processed in last 7 days
- Job success rate (%)
- Job status breakdown

**Use Case:** Monitor system performance, identify bottlenecks, track throughput over time.

#### `get_model_status`
Get status of loaded models, GPU availability, and system configuration.

**Returns:**
- Model loading status (SPAQ, AVA, KONIQ, PAQ2PIQ) - which are loaded
- GPU availability:
  - TensorFlow GPU support and device count
  - PyTorch CUDA availability and device info
  - NVIDIA driver status and GPU names/memory
- Model version information
- Scorer initialization status

**Use Case:** Diagnose GPU/model loading issues, verify system configuration, check if models are ready for scoring.

#### `validate_config`
Validate `config.json` structure and optional input paths; MCP also attempts a DB ping when the database was initialized.

**Returns:**
- `ok` - Boolean (no critical `issues`)
- `issues` - Critical problems (e.g. invalid queue sizes, missing engine-specific DB keys)
- `warnings` - Non-critical (e.g. configured folder path missing on this machine)
- `config_path` - Resolved path to `config.json`
- `database_reachable` - `true` / `false` / `null` (if DB never initialized in this process)

**Checks:**
- Processing queue sizes are positive integers when set
- `database.engine` is `firebird` or `postgres`
- For `firebird`: `database.filename` is non-empty
- For `postgres`: `database.postgres.host|port|dbname|user` are present
- Optional warnings for missing `*_input_path` / `log_dir`

**Use Case:** Verify configuration before starting jobs, catch misconfigurations early.

#### `diagnose_phase_consistency`
Diagnose mismatches between per-image phase status and folder-level aggregates (e.g. UI showing all phases done while an image is still pending).

**Parameters:**
- `image_id` - Image primary key
- `folder_path` - Optional folder path for aggregate comparison

#### `run_processing_job`
Start a background scoring, tagging, or clustering job (requires the corresponding runner to be initialized — typically when the WebUI process has started runners).

**Parameters:**
- `job_type` - `scoring` | `tagging` | `clustering`
- `input_path` - Folder or path (clustering may use empty string for default behavior per runner)
- `args` - Optional dict (e.g. `rescore`, `overwrite`, clustering `threshold`, `time_gap`, `force_rescan`)

#### `find_near_duplicates` / `propagate_tags` / `find_outliers`
Embedding-assisted tools for duplicate pairs, keyword propagation, and outlier detection. See tool docstrings in `modules/mcp_server.py`.

#### `execute_code`
Execute Python in the **WebUI process** over SSE. Requires **`ENABLE_MCP_EXECUTE_CODE=1`** and a Cursor SSE server (**`imgscore-py-sse`** or **`imgscore-el-sse`**). Assign to `result` to return a value.

#### `get_pipeline_stats`
Get statistics about the processing pipeline and active jobs.

**Returns:**
- Runner status (scoring/tagging) with progress
- Queue sizes from configuration
- Processor state (running, progress, job type)
- Active job information

**Use Case:** Monitor active processing, check queue configuration, track job progress in real-time.

## Usage Examples

### From Cursor Chat

Once configured, you can ask Cursor to use these tools:

> "Show me database statistics for my image collection"

> "Find all images with score above 0.9"

> "What's the status of the current scoring job?"

> "Show me images that are missing LIQE scores"

> "Get details for the image at D:\Photos\sunset.jpg"

### Debugging Workflow

1. **Initial Health Check:**
   - Use `get_database_stats` to see image distribution
   - Use `check_database_health` to identify data integrity issues
   - Use `get_error_summary` to see overall error patterns

2. **System Diagnostics:**
   - Use `get_model_status` to verify GPU/models are loaded correctly
   - Use `validate_config` to check configuration validity
   - Use `get_pipeline_stats` to see current processing state

3. **Find Problematic Images:**
   - Use `get_failed_images` to find images with missing scores
   - Use `get_incomplete_images` to find incomplete records
   - Use `validate_file_paths` to find missing files

4. **Monitor Running Jobs:**
   - Use `get_runner_status` to check progress
   - Use `get_recent_jobs` to see job history
   - Use `get_performance_metrics` to track throughput

5. **Investigate Specific Issues:**
   - Use `read_debug_log` to see recent debug entries
   - Use `execute_sql` for custom queries
   - Use `get_error_summary` to see error patterns

6. **Analyze Data:**
   - Use `query_images` with filters to find patterns
   - Use `get_stacks_summary` to check clustering results
   - Use `get_performance_metrics` to analyze processing speed

## Security Notes

- The `execute_sql` tool only allows SELECT queries
- Dangerous SQL patterns (DROP, DELETE, etc.) are blocked
- The server runs locally and doesn't expose network endpoints
- Configuration changes are persisted to config.json

## Troubleshooting

### MCP Server Not Starting

1. Verify MCP SDK is installed:
   ```bash
   pip show mcp
   ```

2. Test the server standalone:
   ```bash
   python -m modules.mcp_server
   ```

3. Check for import errors in `modules/mcp_server.py`

### Tools Not Appearing in Cursor

1. Restart Cursor after configuration changes
2. Check Cursor's MCP server logs for connection errors
3. Verify the working directory path in configuration

### Database Errors

1. Ensure Firebird is reachable per `config.json` → `database` and environment (see project docs)
2. Check file permissions on the database file (when using local/embedded access)
3. Verify no other process has an exclusive lock

## Development

Tools are registered with **FastMCP** (`@mcp.tool`) in [`modules/mcp_server.py`](../../modules/mcp_server.py). After adding or changing a tool, update this document and [`.agent/mcp_tools_reference.md`](../../.agent/mcp_tools_reference.md).
