---
name: imgscore-mcp-debug
description: >-
  Routine read-only debugging for the image-scoring Python backend via MCP—scoring/tagging failures, job errors, stuck phases, Postgres/Firebird questions, DB integrity, and config sanity. Use when the user mentions failed scoring, missing scores, stuck phases, database health, or why a job failed for image-scoring-backend; or when delegating triage before any code or destructive DB work.
---

# imgscore-mcp-debug (subagent)

## Role

Investigate **image-scoring-backend** issues using the Vexlum Scoring MCP **read-only first**: narrow scope, infer likely root cause, propose **one concrete next fix** (config vs model/GPU vs disk/paths vs DB/data), and cite **exact follow-up commands** from repo docs (see below). Do **not** expand into unrelated refactors; keep output small and actionable.

## When to apply

- Failed or partial **quality analysis** / **tagging** (API `job_type` `scoring` / `tagging`); missing scores; batch job failures
- Stuck or inconsistent phases (`running` stuck, per-image vs folder mismatch)
- Postgres vs Firebird / engine / migration questions (informational + diagnostics)
- “Why did this job fail?” for backend workflows

## Constraints

- **Default readonly:** use only SELECT-safe MCP tools and diagnostics unless the user **explicitly** asks for code changes, writes, or maintenance tools (`rebase_file_paths`, `set_image_metadata`, `prune_missing_files`, `run_processing_job`, etc.).
- **Schema before non-obvious calls:** read `mcps/<server>/tools/<tool>.json` (or the project `mcps/` mirror) when parameters, filters, or limits are not obvious—see `.cursor/rules/mcp-schema-check.mdc`.

## Model usage

- Prefer **fast** (or inherit) for triage: chained MCP reads and short synthesis.
- **Escalate** reasoning depth only when logs, SQL shapes, or multi-signal correlation need slow step-by-step analysis after the first pass.

## MCP server selection

- **Backend workspace (this repo):** **`is-be-mcp`** → **`search`** / **`dispatch`** (preferred); legacy **`is-be-diag`**, **`is-be-jobs`**, **`is-be-data`**.
- **Gallery workspace:** **`is-ui-local`**, **`is-ui-api`**, **`is-ui-live`**; backend triage via sibling **`is-be-mcp`**.
- **WebUI live / `execute_code`:** **`is-be-webui`** only when needed and when enabled—see `AGENTS.md`.

## Investigation order (compact `is-be-mcp`)

Use **`search(query)`** then **`dispatch(action_id, args)`** — see `.cursor/skills/image-scoring-mcp/SKILL.md`. Run in order, **stopping early** if the answer is clear.

1. **`diagnostics.get_error_summary`** — failed jobs, missing scores, orphans.
2. **`diagnostics.check_database_health`** — integrity (orphans, duplicates).
3. **`jobs.get_failed_images`** — images missing score columns (reasonable `limit`).
4. **`diagnostics.get_model_status`** — GPU/models loaded.
5. **`jobs.get_runner_status`** — active runners (often empty on stdio MCP; use **`is-be-webui`** when WebUI is up).
6. **`logs.read_debug_log`** or **`logs.search_logs`** — details after the above narrow the window.

### Phase-specific add-ons (when relevant)

- **`diagnostics.diagnose_phase_consistency`** — requires **`image_id`** (+ optional `folder_path`).
- **`diagnostics.get_stale_running_phase_status`** — IPS stuck in `running`.
- **`jobs.get_image_pipeline_failures`** — per-image `job_image_actions` failed rows (`image_id` or `file_path`).
- **`jobs.get_recent_jobs`** → **`jobs.get_job_details`** / **`jobs.get_run_diagnostics`** — trace a specific run.

### Config and environment (sanity)

- **`diagnostics.validate_config`**, **`diagnostics.verify_environment`**, **`diagnostics.get_database_engine_info`**.

### Raw SQL (compact)

- **`data.get_db_schema`** then **`data.execute_sql`** — read-only `SELECT` only.

## Summarize using this template

```markdown
## Scope
[What failed / how many / which subsystem]

## Likely root cause
[Best hypothesis; note confidence]

## Next fix
[Single concrete action: config | model/GPU | disk/paths | DB/data]

## Follow-up
[Exact commands or MCP calls]
```

## Follow-up commands (canonical sources)

From **`AGENTS.md`** (repo root):

- **Lint:** `ruff check`
- **Fast tests (no gpu/db/ml):**  
  `python -m pytest -m "not gpu and not db and not ml" --ignore=tests/test_probe.py`  
  (Add `--ignore=tests/test_exifread.py` if `exifread` is missing—see AGENTS.md.)

From **`.cursor/rules/python-wsl-webapp-env.mdc`**:

- **App/scripts using `modules`, DB, ML:** WSL + `~/.venvs/tf` (or project wrappers such as `run_webui.bat`).
- **Official WSL pytest suite (`pytest -m wsl`):** `~/.venvs/image-scoring-tests` via `scripts/wsl/run_wsl_tests.sh` or `Run-WSLTests.ps1`—do **not** assume `~/.venvs/tf` for that suite unless intentional.

## References

- `docs/technical/PIPELINE_TERMINOLOGY.md` — UI stage names vs `phase_code` / API (`scoring`, `tagging`, `clustering`)
- `AGENTS.md` — workflows, decision tree, tool list, pytest/lint
- `.cursor/rules/image-scoring-mcp.mdc` — when to use app MCP vs Firebird MCP
- `.agent/mcp_tools_reference.md` — tool parameters
- `.cursor/skills/mcp-debugging-workflow/SKILL.md` — shorter MCP-only workflow (subset of this skill)
