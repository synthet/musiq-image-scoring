# AI Agents Configuration

This document describes the AI agents and MCP (Model Context Protocol) server integration for the Image Scoring project.

## Overview

The Image Scoring project provides an MCP server that enables AI agents (like Cursor IDE's AI assistant) to interact with the application for debugging, monitoring, and analysis tasks:

- **Query and analyze** the PostgreSQL database (primary) or legacy Firebird database
- **Monitor** scoring and tagging jobs
- **Diagnose** errors and system issues
- **Track** performance metrics
- **Validate** configuration and file paths
- **Access** debug logs

## SDLC / agent-sdlc

This repo vendors **[agent-sdlc](https://github.com/synthet/agent-sdlc)**-style Cursor rules (`.cursor/rules/`), slash commands (`.cursor/commands/`), and project skills (`.cursor/skills/`). **This `AGENTS.md` file** remains the source of truth for canonical commands, repository layout, and boundaries.

**Cursor slash commands** (type `/` in chat): **`/spec`**, **`/plan`**, **`/implement`**, **`/test-and-fix`**, **`/pr-ready`**, **`/release-notes`**, **`/backup-db`**. This repo also defines **`/release`** (semver release for this backend). **Claude Code** mirrors the agent-sdlc commands under `.claude/commands/`.

## MCP servers (Image Scoring)

The same FastMCP app exposes **44** tools; Cursor can attach it in two ways (separate `mcpServers` entries).

**Unique server names:** Each repo’s `.cursor/mcp.json` uses a workspace prefix so keys do not collide when Cursor merges configs: **`imgscore-py-*`** (Python / `image-scoring` workspace), **`imgscore-el-*`** (`electron-image-scoring` workspace). Shared tools such as Playwright or Firebird use the same prefix (`imgscore-py-playwright`, `imgscore-el-firebird`, …).

### Configuration

Server key meanings:

- **`imgscore-py-stdio`**: **Python** workspace — **stdio** with `cwd` / `PYTHONPATH` = `${workspaceFolder}`.
- **`imgscore-py-postgres`**: **PostgreSQL** administration — use `toolbox.exe --prebuilt postgres` to manage the DB.
- **`imgscore-el-stdio`**: **Electron** workspace — **stdio** with `cwd` / `PYTHONPATH` = sibling **image-scoring** (fixed path).
- **`imgscore-py-sse`** / **`imgscore-el-sse`**: same WebUI **SSE** URL (`/mcp/sse`); use the key from the workspace you have open. Enables **`execute_code`** when `ENABLE_MCP_EXECUTE_CODE=1`.

**Example — Python workspace** (`.cursor/mcp.json` in `image-scoring`):

```json
{
  "mcpServers": {
    "imgscore-py-stdio": {
      "command": "python",
      "args": ["-m", "modules.mcp_server"],
      "cwd": "${workspaceFolder}",
      "env": { "PYTHONPATH": "${workspaceFolder}" }
    },
    "imgscore-py-sse": {
      "url": "http://127.0.0.1:7860/mcp/sse"
    }
  }
}
```

**Example — Electron workspace** (`.cursor/mcp.json` in `electron-image-scoring`): **`imgscore-el-stdio`** for stdio (same `command`/`args` as `imgscore-py-stdio`, but `cwd` / `PYTHONPATH` = absolute path to **image-scoring**), plus **`imgscore-el-sse`** for the same SSE URL when the WebUI is running.

For SSE, start the WebUI first (`run_webui.bat` or `python webui.py`). Confirm the URL with **`GET /mcp-status`** → `expected_sse_url` if the port is not 7860. For **`execute_code`**, set **`ENABLE_MCP_EXECUTE_CODE=1`** on the WebUI process.

### Setup for Cursor IDE

1. **Copy configuration** to Cursor's MCP settings:
   - Windows: `%APPDATA%\Cursor\User\globalStorage\cursor.mcp\mcp.json`
   - Or merge `mcp_config.json` contents into your existing MCP configuration

2. **Install MCP SDK** (if not already installed):
   ```bash
   pip install mcp
   ```

3. **Restart Cursor IDE** to load the new MCP server

### Running the MCP Server

#### Standalone Mode

```bash
# Direct Python execution
python -m modules.mcp_server

# Using PowerShell script
.\scripts\powershell\Run-MCPServer.ps1

# Using batch file
scripts\batch\run_mcp_server.bat
```

#### Integrated with WebUI

Set environment variable to enable MCP alongside the WebUI:

```powershell
# Windows PowerShell
$env:ENABLE_MCP_SERVER = "1"
python webui.py

# Linux/WSL
ENABLE_MCP_SERVER=1 python webui.py
```

## Available Tools

The MCP server registers **44** tools (see [`modules/mcp_server.py`](modules/mcp_server.py)). Summary:

### Diagnostic

| Tool | Description |
|------|-------------|
| `get_error_summary` | Overview of failed jobs, missing scores, orphans |
| `check_database_health` | Data integrity (orphans, duplicates, inconsistencies) |
| `get_model_status` | GPU / PyTorch / TensorFlow / model load status |
| `diagnose_phase_consistency` | Per-image vs folder phase status mismatches |
| `get_stale_running_phase_status` | `image_phase_status` rows stuck in `running` (age filter) |
| `get_migration_parity` | Firebird↔Postgres parity snapshot (when applicable) |
| `verify_environment` | Host, Python, and key dependency sanity check |

### Data query

| Tool | Description |
|------|-------------|
| `get_database_stats` | Counts, score distributions, averages |
| `query_images` | Filtered listing (scores, rating, label, folder, etc.) |
| `get_image_details` | Full row for a `file_path` |
| `search_images_by_hash` | Lookup by `image_hash` (content hash) |
| `execute_sql` | Read-only `SELECT` only |

### Errors & paths

| Tool | Description |
|------|-------------|
| `get_failed_images` | Missing key scores (general, technical, spaq, koniq, …) |
| `get_incomplete_images` | Broader “incomplete” rows (scores, rating, label) |
| `validate_file_paths` | Spot-check files on disk |
| `summarize_directory` | File counts and sizes under a folder path |
| `search_missing_sidecars` | NEF files missing companion XMP in a directory |

### Performance & jobs

| Tool | Description |
|------|-------------|
| `get_performance_metrics` | Job duration, throughput, success rate (recent window) |
| `get_runner_status` | Scoring / tagging / clustering / selection runners |
| `get_recent_jobs` | Job history |
| `get_job_details` | Single job/run by id (`jobs.id`, same as API workflow `run_id`) |
| `get_job_phases` | Phase plan/status rows for a job |
| `get_job_stage_images` | Per-image work items for a job+phase (`include_steps` optional) |
| `get_pipeline_stats` | Runner + dispatcher + queue config snapshot |
| `run_processing_job` | Start scoring, tagging, or clustering job (requires runners; WebUI/SSE typical for scoring/tagging) |

### HTTP, engine, embeddings, stacks

| Tool | Description |
|------|-------------|
| `probe_backend_http` | Time a GET to a relative WebUI path (e.g. `/api/scope/tree`) |
| `get_database_engine_info` | Configured engine, connector, safe connection targets, ping |
| `get_embedding_stats` | Images with vs without embeddings; optional folder filter |
| `check_stack_invariants` | Singleton stacks, orphan stack references, empty stacks |

### Config & logs

| Tool | Description |
|------|-------------|
| `validate_config` | Structural config checks + optional DB ping (`database_reachable`) |
| `get_config` | Full `config.json` |
| `set_config_value` | Persist a single key (dot paths supported) |
| `read_debug_log` | Tail of debug log |

### Folders, stacks, similarity

| Tool | Description |
|------|-------------|
| `get_folder_tree` | Folders with image counts |
| `get_stacks_summary` | Stack/cluster summary |
| `get_gallery_status` | Gallery UI wiring status when exposed by WebUI |
| `search_similar_images` | Embedding cosine similarity to an example image |
| `find_near_duplicates` | Near-duplicate pairs in a folder |
| `propagate_tags` | Propagate keywords to neighbors (supports `dry_run`) |
| `find_outliers` | Atypical images via embedding stats |

### Maintenance (writes)

| Tool | Description |
|------|-------------|
| `rebase_file_paths` | Batch-update image paths by root prefix (`dry_run` default) |
| `set_image_metadata` | Update rating/label for an image path |
| `prune_missing_files` | Drop DB rows for files missing on disk (`dry_run` default) |

### Execute code (SSE + opt-in)

| Tool | Description |
|------|-------------|
| `execute_code` | `exec` in WebUI process (`gr`, `demo`, `components`, runners, `db`, `config`). Requires Cursor server **`imgscore-py-sse`** or **`imgscore-el-sse`** (same endpoint), WebUI running, and **`ENABLE_MCP_EXECUTE_CODE=1`**. Assign to `result` to return a value. |

## Common Workflows

### Workflow 1: Investigate Scoring Failures

```
1. get_error_summary → Identify scope of failures
2. get_failed_images → Get specific failed images
3. get_model_status → Check if GPU/models are working
4. get_runner_status → Check if job is still running
5. read_debug_log → See detailed error messages
```

### Workflow 2: System Health Check

```
1. check_database_health → Data integrity
2. get_model_status → System configuration
3. validate_config → Configuration validity
4. get_performance_metrics → Performance baseline
5. validate_file_paths → File system consistency
```

### Workflow 3: Performance Investigation

```
1. get_performance_metrics → Current performance stats
2. get_recent_jobs → Recent job history
3. get_pipeline_stats → Current pipeline state
4. get_runner_status → Active job details
5. execute_sql → Custom performance queries if needed
```

### Workflow 4: Data Quality Audit

```
1. get_database_stats → Overall statistics
2. check_database_health → Integrity issues
3. get_incomplete_images → Missing data
4. validate_file_paths → Missing files
5. get_error_summary → Error patterns
```

## Quick Decision Tree

**"Why did scoring fail?"**
→ `get_error_summary` → `get_failed_images` → `get_model_status` → `read_debug_log`

**"Is the system healthy?"**
→ `check_database_health` → `get_model_status` → `validate_config`

**"How fast is processing?"**
→ `get_performance_metrics` → `get_runner_status` → `get_pipeline_stats`

**"Find images with X property"**
→ `query_images` with filters → `get_image_details` for specifics

**"What's in the database?"**
→ `get_database_stats` → `get_folder_tree` → `get_stacks_summary`

## Important Notes

- **Database Tools**: Most tools require database access. If database is unavailable, they return a clear error message.
- **Non-DB tools**: `get_model_status`, `probe_backend_http`, `get_database_engine_info`, and `verify_environment` do not require a DB for their main output. `get_pipeline_stats` mostly uses config + in-process runners (partial without DB). `validate_config` runs structural checks without DB; when the DB is initialized, the MCP tool adds `database_reachable`.
- **Safety**: `execute_sql` only allows SELECT queries. Dangerous operations are blocked.
- **Performance**: Some tools (like `validate_file_paths`) can be slow on large datasets. Use `limit` parameter.
- **Real-time**: `get_runner_status` and `get_pipeline_stats` show current state, others query historical data.
- **execute_code**: Only works when Cursor uses **`imgscore-py-sse`** or **`imgscore-el-sse`**, Gradio context is present, and **`ENABLE_MCP_EXECUTE_CODE=1`**. Assign to `result` in your code to return a value. Dev/debug use only.

## Tool Availability

All tools are available when:
- MCP server is running (via Cursor IDE or standalone)
- Database is initialized (for DB-requiring tools)
- Runners are set (for `get_runner_status`, `get_pipeline_stats`, `run_processing_job`)

## Documentation References

- **[Agent Coordination](docs/technical/AGENT_COORDINATION.md)** - Integration and coordination guide for AI agents
- **[MCP Tools Reference](.agent/mcp_tools_reference.md)** - Quick reference guide for AI agents
- **[MCP Debugging Tools](docs/technical/MCP_DEBUGGING_TOOLS.md)** - Detailed documentation
- **[DB Schema](docs/technical/DB_SCHEMA.md)** - Database schema reference
- **[Migration Plan](docs/plans/database/FIREBIRD_POSTGRES_MIGRATION.md)** - Firebird→PostgreSQL migration status
- **[AI Edit Spec](.agent/ai_edit_spec.md)** - Guidelines for AI agents editing code

## Example Agent Interactions

### Example 1: Check System Health

```
Agent: "Check if the system is healthy"
→ Uses: check_database_health, get_model_status, validate_config
→ Returns: Health status, any issues found
```

### Example 2: Find Failed Images

```
Agent: "Find all images that failed scoring"
→ Uses: get_error_summary, get_failed_images
→ Returns: List of failed images with error details
```

### Example 3: Performance Analysis

```
Agent: "How fast is the system processing images?"
→ Uses: get_performance_metrics, get_runner_status
→ Returns: Processing speed, success rates, current job progress
```

## Troubleshooting

### MCP Server Not Available

1. Check if MCP SDK is installed: `pip install mcp`
2. Verify configuration in Cursor IDE settings
3. Check if server is running: `python -m modules.mcp_server`
4. Review logs for connection errors

### Database Tools Return Errors

1. Verify database is initialized: Check `get_model_status` (non-DB tool)
2. Check database connection settings in config (`database.engine`, `database.postgres.*`)
3. Ensure PostgreSQL is running (`docker compose up -d`) or Firebird is accessible (legacy mode)

### Tools Not Appearing in Cursor

1. Restart Cursor IDE after configuration changes
2. Verify `mcp_config.json` syntax is valid JSON
3. Check Cursor IDE console for MCP server errors
4. Ensure Python environment has MCP SDK installed

### Duplicate MCP servers in Cursor (same name twice)

If you still see two **`playwright`**, two **`image-scoring-mcp-sse`**, etc., your **user-level** MCP config is probably merging with **project** `.cursor/mcp.json` and reusing old keys. Open `%APPDATA%\Cursor\User\globalStorage\cursor.mcp\mcp.json` (or Cursor Settings → MCP) and **remove or rename** duplicates, or align them with the **`imgscore-py-*` / `imgscore-el-*`** keys from this repo.

## Future Enhancements

Potential additions to the MCP server:
- Batch operations (bulk updates, exports)
- Advanced analytics (trends, correlations)
- Configuration templates and presets

## Cursor Cloud specific instructions

### Environment overview

This is a Python 3.12 project using a virtualenv at `.venv/`. The main application is a **FastAPI + Gradio** server (`python webui.py`) on port 7860 backed by **PostgreSQL + pgvector** (primary, local Docker on port 5432). A legacy **Firebird 5.0** database is retained for Electron frontend compatibility (Phase 4 migration pending).

### Firebird 5.0 setup (required for legacy/Electron compatibility only)

Firebird 5.0 is installed at `/opt/firebird/`. Before starting the WebUI or running DB-dependent tests, the Firebird server must be running:

```bash
export LD_LIBRARY_PATH=/opt/firebird/lib:$LD_LIBRARY_PATH
/opt/firebird/bin/firebird -a -d &
```

If the database file (`scoring_history.fdb`) does not exist, create it:

```bash
/opt/firebird/bin/isql -user sysdba -password masterkey <<< "CREATE DATABASE '/workspace/scoring_history.fdb' PAGE_SIZE 16384;"
```

### Starting the WebUI

```bash
source /workspace/.venv/bin/activate
export LD_LIBRARY_PATH=/opt/firebird/lib:$LD_LIBRARY_PATH
WEBUI_HOST=0.0.0.0 \
FIREBIRD_CLIENT_LIBRARY=/opt/firebird/lib/libfbclient.so \
FIREBIRD_USE_LOCAL_PATH=1 \
python webui.py
```

Key env vars:
- `FIREBIRD_USE_LOCAL_PATH=1` — uses embedded/local file access instead of TCP to a Windows host (critical in Cloud VMs)
- `FIREBIRD_CLIENT_LIBRARY=/opt/firebird/lib/libfbclient.so` — points to the Firebird 5.0 client library
- `WEBUI_HOST=0.0.0.0` — binds to all interfaces for browser access

### Running tests

```bash
source /workspace/.venv/bin/activate
python -m pytest -m "not gpu and not db and not ml and not firebird" --ignore=tests/test_probe.py
```

- `tests/test_probe.py` must be ignored — it executes DB calls at import time and crashes collection.
- Some tests in `test_culling.py` and `test_db_consistency.py` are missing the `db`/`firebird` marker and will ERROR during collection; this is a pre-existing issue.
- Some tests may be slow (e.g., `test_events.py::test_websocket_connection` can hang); use `timeout` if needed.

### Linting

```bash
source /workspace/.venv/bin/activate
ruff check
```

`ruff` is included in the pinned dependencies. There is no `ruff.toml` or `[tool.ruff]` config — it uses defaults. Pre-existing lint warnings (755+) are expected.

### Gotchas

- The base `requirements.txt` pins `tensorflow-cpu>=2.15.1,<2.16.0` which is **incompatible with Python 3.12**. Use `requirements/requirements_wsl_gpu.txt` (filtered to remove NVIDIA/CUDA packages) for installing deps on Python 3.12.
- The DB migration in `_init_db_impl()` may log errors about missing columns (`CULL_DECISION`, `RATING`) when creating a fresh database. The server still starts and serves API requests.
- No `config.json` ships with the repo — it is created at runtime. The app handles its absence gracefully.
- After installing Firebird, `/tmp/firebird/` files are owned by the `firebird` user. Run `sudo chmod -R 777 /tmp/firebird/` before using `isql` as a non-firebird user, or the client will fail with "Permission denied" on `fb_init`/`fb50_trace`.
- `tests/test_exifread.py` may also fail collection if the `exifread` package is not installed; add `--ignore=tests/test_exifread.py` alongside `test_probe.py` when running the fast test subset.
