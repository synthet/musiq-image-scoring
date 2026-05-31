# AI Agents Configuration

This document describes the AI agents and MCP (Model Context Protocol) server integration for **Vexlum Scoring** (`image-scoring-backend`).

## Overview

**Vexlum Scoring** provides an MCP server that enables AI agents (like Cursor IDE's AI assistant) to interact with the application for debugging, monitoring, and analysis tasks:

- **Query and analyze** the PostgreSQL database (primary)
- **Monitor** scoring and tagging jobs
- **Diagnose** errors and system issues
- **Track** performance metrics
- **Validate** configuration and file paths
- **Access** debug logs

## Infra quick reference

For **doctor CLI**, redacted debug bundles, safe commands, and pitfalls (without duplicating the MCP catalog below), see **[.agent/INFRA_QUICKSTART.md](.agent/INFRA_QUICKSTART.md)** and **[docs/DIAGNOSTICS.md](docs/DIAGNOSTICS.md)**.

**Agent infra:** [.agent/AGENT_INFRA_INVENTORY.md](.agent/AGENT_INFRA_INVENTORY.md) — catalog of rules, skills, workflows; [.agent/COMMANDS.md](.agent/COMMANDS.md); [.agent/SAFETY.md](.agent/SAFETY.md); [.agent/subagents/README.md](.agent/subagents/README.md); [.agent/workflows/](.agent/workflows/).

## SDLC / agent-sdlc

This repo vendors **[agent-sdlc](https://github.com/synthet/agent-sdlc)**-style Cursor rules (`.cursor/rules/`), slash commands (`.cursor/commands/`), and project skills (`.cursor/skills/`). **This `AGENTS.md` file** remains the source of truth for canonical commands, repository layout, and boundaries.

### Agent skills: source of truth (AST10)

For [OWASP Agentic Skills Top 10](https://github.com/kenhuangus/agentic-skills-top-10) cross-platform drift (**AST10**), duplicated skills follow this rule:

- **Canonical:** [`.cursor/skills/<name>/SKILL.md`](.cursor/skills/) — edit here first for any skill that exists under both trees.
- **Mirror:** [`.claude/skills/<name>/SKILL.md`](.claude/skills/) — must match the canonical file in the **same PR** when you change that skill (byte-for-byte or intentionally identical content).
- **Agent-only (no Claude mirror):** [`.agent/skills/`](.agent/skills/) — not duplicated under `.claude/skills/`; Cursor discovers these separately.

**Inventory and PR review:** [.agent/SKILL_INVENTORY.md](.agent/SKILL_INVENTORY.md) · [.agent/SKILL_CHANGE_AST10_REVIEW.md](.agent/SKILL_CHANGE_AST10_REVIEW.md)

**Cursor slash commands** (type `/` in chat): **`/spec`**, **`/plan`**, **`/implement`**, **`/test-and-fix`**, **`/pr-ready`**, **`/task-claim`**, **`/release-notes`**, **`/release`**, **`/backup-db`**, **`/critical-commit-audit`**, **`/wiki-ingest`**, **`/wiki-lint`**, **`/wiki-query`**, **`/check-subagents`**, **`/run-codex-review`**, **`/run-gemini-review`**, **`/run-subagent-review`**. Index: [`.cursor/README.md`](.cursor/README.md). **Claude Code** mirrors paired commands under `.claude/commands/`.

**External CLI reviews:** sibling [`subagent-orchestrator`](../subagent-orchestrator) via MCP **`imgscore-subagent-orchestrator`** — see [docs/technical/EXTERNAL_CLI_REVIEWS.md](docs/technical/EXTERNAL_CLI_REVIEWS.md).

## MCP servers (Vexlum Scoring)

The same FastMCP app exposes **54** tools; Cursor attaches via **two project servers** (stdio + live SSE).

**Naming:** all project MCP keys use prefix **`image-scoring-`**. User `~/.cursor/mcp.json` holds cross-repo tools only (`github`, `subagent-orchestrator`, …) — **not** `image-scoring-*`.

| Cursor server key | Transport | Repo | Requires running app? |
|-------------------|-----------|------|------------------------|
| **`image-scoring-backend-stdio`** | stdio | backend [`.cursor/mcp.json`](.cursor/mcp.json) | No |
| **`image-scoring-backend-webui`** | SSE | backend `.cursor/mcp.json` | Yes — `run_webui.bat` |
| **`image-scoring-backend-postgres`** | stdio | backend `.cursor/mcp.json` (disabled) | No |
| **`image-scoring-gallery-stdio`** | stdio | gallery `.cursor/mcp.json` | No |
| **`image-scoring-gallery-live`** | SSE | gallery `.cursor/mcp.json` | Yes — Electron dev / `ENABLE_GALLERY_MCP_SSE` |

Example templates: [`.cursor/mcp.pair.example.json`](.cursor/mcp.pair.example.json) (backend), gallery [`.cursor/mcp.pair.example.json`](https://github.com/synthet/image-scoring-gallery/blob/main/.cursor/mcp.pair.example.json).

For backend WebUI SSE, start the WebUI first (`run_webui.bat`). Confirm URL with **`GET /mcp-status`** → `expected_sse_url`. For **`execute_code`**, set **`ENABLE_MCP_EXECUTE_CODE=1`**. Gallery live port: **`gallery-mcp.lock`** in gallery repo root (default `9373`).

### Setup for Cursor IDE

1. **Copy configuration** to Cursor's MCP settings:
   - Windows: `%USERPROFILE%\.cursor\mcp.json`
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

The MCP server registers **53** tools (see [`modules/mcp_server.py`](modules/mcp_server.py)). Summary:

### Diagnostic

| Tool | Description |
|------|-------------|
| `get_error_summary` | Overview of failed jobs, missing scores, orphans, plus `stale_running_count` (phase rows stuck `running`) |
| `check_database_health` | Data integrity (orphans, duplicates, inconsistencies) |
| `get_model_status` | GPU / PyTorch / TensorFlow / model load status |
| `diagnose_phase_consistency` | Per-image vs folder phase status mismatches |
| `get_stale_running_phase_status` | `image_phase_status` rows stuck in `running` (age filter) |
| `verify_environment` | Host, Python, and key dependency sanity check |
| `get_system_resources` | Live CPU / RAM and optional `nvidia-smi` GPU snapshot |

### Data query

| Tool | Description |
|------|-------------|
| `get_database_stats` | Counts, score distributions, averages |
| `query_images` | Filtered listing (scores, rating, label, folder, etc.) |
| `get_image_details` | Full row for a `file_path` |
| `search_images_by_hash` | Lookup by `image_hash` (content hash) |
| `get_db_schema` | PostgreSQL `information_schema` columns (for drafting `execute_sql`) |
| `execute_sql` | Read-only `SELECT` / `WITH … SELECT` (parameterized `?` placeholders) |

### Errors & paths

| Tool | Description |
|------|-------------|
| `get_failed_images` | Missing key scores (general, technical, spaq, koniq, …) |
| `get_incomplete_images` | Broader “incomplete” rows (scores, rating, label) |
| `validate_file_paths` | Spot-check files on disk; optional `folder_path` and `missing_only` |

### Performance & jobs

| Tool | Description |
|------|-------------|
| `get_performance_metrics` | Job duration, throughput, success rate (recent window) |
| `get_runner_status` | Scoring / tagging / clustering / selection runners |
| `get_recent_jobs` | Job history |
| `get_job_details` | Single job/run by id (`jobs.id`, same as API workflow `run_id`) |
| `get_job_phases` | Phase plan/status rows for a job |
| `get_job_stage_images` | Per-image work items for a job+phase (`include_steps` optional) |
| `get_job_execution_report` | Action-level report + `summary.action_counts` (processed / skipped / failed, …) |
| `get_run_diagnostics` | Post-run audit + per-phase `image_phase_status` counts for `run_id` |
| `get_image_pipeline_failures` | Per-image `job_image_actions` rows with `failed` (by `image_id` or `file_path`) |
| `get_location_stats` | GPS / geocode coverage counts on `image_exif` |
| `export_debug_bundle` | Redacted support zip (same bundle as `scripts/export_debug_bundle.py`) |
| `get_pipeline_stats` | Runner + dispatcher + queue config snapshot |
| `run_processing_job` | Start scoring, tagging, or clustering job (requires runners; WebUI/SSE typical for scoring/tagging); returns integer `jobs.id` |
| `manage_runners` | `stop` / `status` for in-process runners (WebUI context); not for starting jobs |

### Engine, embeddings, stacks

| Tool | Description |
|------|-------------|
| `get_database_engine_info` | Configured engine, connector, safe connection targets, ping |
| `get_embedding_stats` | Images with vs without embeddings; optional folder filter |
| `check_stack_invariants` | Singleton stacks, orphan stack references, empty stacks |

### Config & logs

| Tool | Description |
|------|-------------|
| `validate_config` | Structural config checks + optional DB ping (`database_reachable`) |
| `get_config` | `config.json` merged view with sensitive keys redacted |
| `set_config_value` | Persist a single key (dot paths supported) |
| `read_debug_log` | Tail of `debug.log` (JSON lines + `raw` fallback) |
| `get_server_log_tail` | Tails `webui.log` and/or `debug.log` (same as `GET /api/status/log-tails`) |
| `search_logs` | Regex search over recent log tails (`webui` / `debug` / `all`) with context lines |

### Folders, stacks, similarity

| Tool | Description |
|------|-------------|
| `get_folder_tree` | Folders with image counts |
| `get_stacks_summary` | Stack/cluster summary |
| `search_similar_images` | Embedding cosine similarity to an example image |
| `search_images_by_text` | Free-text semantic search via CLIP text-to-image similarity |
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
| `execute_code` | `exec` in WebUI process. Requires **`image-scoring-backend-webui`**, WebUI running, and **`ENABLE_MCP_EXECUTE_CODE=1`**. Assign to `result` to return a value. |

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

## Git Configuration — Do Not Modify

**Never modify `.git/config`** — do not set `extensions.worktreeConfig`, change `core.repositoryformatversion`, or add any git extensions. Third-party tools (Gemini Code Assist / Antigravity) use embedded git libraries that fail on non-standard extensions, breaking workspace resolution. If a worktree is needed, use a temporary one and clean it up immediately — do not leave worktree config persisted in the repo.

## Important Notes

- **Database Tools**: Most tools require database access. If database is unavailable, they return a clear error message.
- **Non-DB tools**: `get_model_status`, `get_database_engine_info`, `verify_environment`, `get_system_resources`, and `search_logs` do not require a DB for their main output. `get_pipeline_stats` mostly uses config + in-process runners (partial without DB). `validate_config` runs structural checks without DB; when the DB is initialized, the MCP tool adds `database_reachable`.
- **Safety**: `execute_sql` only allows SELECT queries. Dangerous operations are blocked.
- **Performance**: Some tools (like `validate_file_paths`) can be slow on large datasets. Use `limit` parameter.
- **Real-time**: `get_runner_status` and `get_pipeline_stats` show current state, others query historical data.
- **execute_code**: Only works when Cursor uses **`image-scoring-backend-webui`**, Gradio context is present, and **`ENABLE_MCP_EXECUTE_CODE=1`**. Assign to `result` in your code to return a value. Dev/debug use only.

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
- **[Migration Plan](docs/planning/database/FIREBIRD_POSTGRES_MIGRATION.md)** - Firebird→PostgreSQL migration status
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
3. Ensure PostgreSQL is running (`docker compose up -d`)

### Tools Not Appearing in Cursor

1. Restart Cursor IDE after configuration changes
2. Verify `mcp_config.json` syntax is valid JSON
3. Check Cursor IDE console for MCP server errors
4. Ensure Python environment has MCP SDK installed

### Duplicate MCP servers in Cursor (same name twice)

If you still see duplicate or legacy keys (`scoring`, `webui`, `imgscore-py-*`), remove them from **`%USERPROFILE%\.cursor\mcp.json`**. Project keys belong only in each repo’s `.cursor/mcp.json`.

## Pytest E2E vocabulary (agents)

Users and docs sometimes overload **“E2E.”** Map phrases to suites as follows:

| User / chat phrase | Canonical suite name | Paths | Marker / opt-in | How to run (WSL + `~/.venvs/tf` typical; see `.cursor/rules/python-wsl-webapp-env.mdc`) |
|--------------------|----------------------|-------|-----------------|----------------------------------------------------------------------------------------|
| **Integration E2E**, **API E2E**, **runs submit E2E**, **postgres E2E** | Postgres API E2E | `tests/integration/test_runs_*_e2e.py` | `@pytest.mark.postgres`; enable with **`RUN_POSTGRES_TESTS=1`** or **`pytest -m postgres`** | `pytest tests/integration/ -m postgres -v` (requires PostgreSQL reachable for `image_scoring_test`; see `tests/conftest.py`) |
| **Docker E2E**, **inference E2E**, **GPU E2E in Docker**, **`e2e-inference` profile** | Docker inference E2E | `tests/e2e_docker/` | `@pytest.mark.inference_e2e` + **`IMAGE_SCORING_DOCKER_INFERENCE_E2E=1`** | `docker compose --profile e2e-inference run --rm inference-e2e` (runs `scripts/docker_inference_e2e.sh` → pytest `-m inference_e2e`). Not the same as integration E2E. |
| **Unit tests**, **fast tests** (not E2E) | Default / fast subset | Most tests outside the two rows above | Exclude heavy markers | `pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py` |

**Disambiguation:** The phrase **“e2e unit tests”** is ambiguous (some people mean integration E2E; others misspeak for unit tests). If the user does not specify, **ask once**: Postgres API E2E (`tests/integration/*_e2e.py`), Docker inference E2E (`tests/e2e_docker/`), or ordinary unit/fast pytest?

## Future Enhancements

Potential additions to the MCP server:
- Batch operations (bulk updates, exports)
- Advanced analytics (trends, correlations)
- Configuration templates and presets

## Cursor Cloud specific instructions

### Environment overview

This is a Python 3.12 project using a virtualenv at `.venv/`. The main application is a **FastAPI + Gradio** server (`python webui.py`) on port 7860 backed by **PostgreSQL + pgvector** (primary, local Docker on port 5432).


### Starting the WebUI

```bash
source /workspace/.venv/bin/activate
WEBUI_HOST=0.0.0.0 python webui.py
```

Key env vars:
- `WEBUI_HOST=0.0.0.0` — binds to all interfaces for browser access

### Running tests

See **Pytest E2E vocabulary (agents)** above for **Postgres API E2E** vs **Docker inference E2E** vs fast unit runs.

```bash
source /workspace/.venv/bin/activate
python -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py
```

- `tests/test_probe.py` must be ignored — it executes DB calls at import time and crashes collection.
- Some tests in `test_culling.py` and `test_db_consistency.py` are missing the `db` marker and will ERROR during collection; this is a pre-existing issue.
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
- After installing PostgreSQL, ensure it is reachable.
- `tests/test_exifread.py` may also fail collection if the `exifread` package is not installed; add `--ignore=tests/test_exifread.py` alongside `test_probe.py` when running the fast test subset.

## Generated MCP Tool Inventory

<!-- BEGIN MCP TOOL INVENTORY -->
_This section is auto-generated by `python scripts/generate_mcp_tool_inventory.py --update-docs AGENTS.md docs/technical/MCP_DEBUGGING_TOOLS.md`. Do not edit manually._

Tool count: **54**

| Tool | Signature |
|---|---|
| `get_database_stats` | `()` |
| `query_images` | `(limit: int = 20, offset: int = 0, sort_by: str = 'created_at', order: str = 'desc', min_score: Optional[float] = None, max_score: Optional[float] = None, rating: Optional[int] = None, label: Optional[str] = None, keyword: Optional[str] = None, folder_path: Optional[str] = None)` |
| `get_image_details` | `(file_path: str)` |
| `search_images_by_hash` | `(image_hash: str, hash_version: Optional[int] = None)` |
| `get_db_schema` | `(table_name_prefix: Optional[str] = None, max_tables: int = 200, max_column_rows: int = 8000)` |
| `execute_sql` | `(query: str, params: list = None)` |
| `get_folder_tree` | `(root_path: Optional[str] = None)` |
| `get_newly_imported_folders` | `(days: int = 7, min_images: int = 1, path_pattern: Optional[str] = None)` |
| `process_newly_imported_folders` | `(days: int = 7, job_type: str = 'scoring', path_pattern: Optional[str] = None)` |
| `get_stacks_summary` | `(folder_path: Optional[str] = None)` |
| `get_incomplete_images` | `(limit: int = 100)` |
| `get_failed_images` | `(limit: int = 50, offset: int = 0)` |
| `get_error_summary` | `()` |
| `check_database_health` | `()` |
| `validate_file_paths` | `(limit: int = 100, folder_path: Optional[str] = None, missing_only: bool = False)` |
| `diagnose_phase_consistency` | `(image_id: int, folder_path: Optional[str] = None)` |
| `get_stale_running_phase_status` | `(min_age_seconds: int = 3600, limit: int = 50)` |
| `get_recent_jobs` | `(limit: int = 10)` |
| `get_job_details` | `(job_id: int)` |
| `get_job_phases` | `(job_id: int)` |
| `get_job_stage_images` | `(job_id: int, phase_code: str, limit: int = 50, offset: int = 0, include_steps: bool = False)` |
| `get_run_diagnostics` | `(run_id: int)` |
| `get_drive_diagnostics` | `()` |
| `get_job_execution_report` | `(run_id: int, phase_code: Optional[str] = None, action: Optional[str] = None, offset: int = 0, limit: int = 20)` |
| `get_image_pipeline_failures` | `(image_id: Optional[int] = None, file_path: Optional[str] = None, limit: int = 50)` |
| `get_location_stats` | `()` |
| `export_debug_bundle` | `(output_path: Optional[str] = None)` |
| `get_embedding_stats` | `(folder_path: Optional[str] = None, embedding_space: Optional[str] = None)` |
| `get_database_engine_info` | `()` |
| `check_stack_invariants` | `(limit: int = 20)` |
| `rebase_file_paths` | `(old_root: str, new_root: str, dry_run: bool = True)` |
| `set_image_metadata` | `(file_path: str, rating: Optional[int] = None, label: Optional[str] = None)` |
| `prune_missing_files` | `(dry_run: bool = True)` |
| `verify_environment` | `()` |
| `get_system_resources` | `()` |
| `get_thread_dump` | `()` |
| `get_runner_status` | `()` |
| `get_pipeline_stats` | `()` |
| `get_performance_metrics` | `(days: int = 7)` |
| `get_model_status` | `()` |
| `run_processing_job` | `(job_type: str, input_path: str, args: dict = None)` |
| `manage_runners` | `(runner: str, operation: str)` |
| `get_config` | `()` |
| `validate_config` | `()` |
| `set_config_value` | `(key: str, value: Any)` |
| `read_debug_log` | `(lines: int = 100)` |
| `get_server_log_tail` | `(sources: str = 'all', lines: int = 100)` |
| `search_logs` | `(pattern: str, sources: str = 'all', context_lines: int = 2, max_lines_scan: int = 25000, max_matches_per_file: int = 40, case_insensitive: bool = True)` |
| `search_similar_images` | `(example_path: Optional[str] = None, example_image_id: Optional[int] = None, limit: int = 20, folder_path: Optional[str] = None, min_similarity: Optional[float] = None, embedding_space: Optional[str] = None)` |
| `search_images_by_text` | `(query: str, limit: int = 20, folder_path: Optional[str] = None, folder_ids: Optional[list[int]] = None, min_similarity: Optional[float] = None, min_rating: Optional[int] = None, color_label: Optional[str] = None, keyword: Optional[str] = None, captured_date: Optional[str] = None, sort_by: Optional[str] = None, order: Optional[str] = None)` |
| `find_near_duplicates` | `(threshold: Optional[float] = None, folder_path: Optional[str] = None, limit: Optional[int] = None)` |
| `propagate_tags` | `(folder_path: Optional[str] = None, dry_run: bool = True, k: Optional[int] = None, min_similarity: Optional[float] = None, min_keyword_confidence: Optional[float] = None)` |
| `find_outliers` | `(folder_path: str = '', z_threshold: Optional[float] = None, k: Optional[int] = None, limit: Optional[int] = None)` |
| `execute_code` | `(code: str)` |
<!-- END MCP TOOL INVENTORY -->
