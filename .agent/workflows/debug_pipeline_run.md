---
description: Debug a pipeline run / job — phases, actions, IPS
---

## Purpose

Investigate **runs** (`jobs` rows): failed phases, stuck `running` status, per-image actions.

## When to use

- A run failed partway; UI shows inconsistent counts; missing scores after a job.

## Canonical docs first

- [docs/technical/PIPELINE_TERMINOLOGY.md](../../docs/technical/PIPELINE_TERMINOLOGY.md)
- [docs/IMAGE_PIPELINE.md](../../docs/IMAGE_PIPELINE.md)
- [.cursor/agents/imgscore-mcp-debug.md](../../.cursor/agents/imgscore-mcp-debug.md)

## Safe commands / MCP order (read-only)

1. `get_error_summary`
2. `get_recent_jobs` → `get_job_details` → `get_job_phases`
3. `get_run_diagnostics` (for `run_id`)
4. `get_job_execution_report`
5. `get_image_pipeline_failures` (by `image_id` or `file_path`)
6. `diagnose_phase_consistency`, `get_stale_running_phase_status` if phases look stuck
7. `read_debug_log` / `search_logs`

Exact tool names and parameters: `mcps/project-0-image-scoring-image-scoring/tools/*.json` and [AGENTS.md](../../AGENTS.md).

## Files commonly touched (fixes)

- `modules/job_dispatcher.py`, `modules/phase_executors.py`, `modules/engine.py`, phase runners

## Common failure modes

- Stale `image_phase_status` rows stuck `running`.
- Runner not started; GPU OOM; path not visible from WSL.

## Do not

- Do not invoke `run_processing_job` or `manage_runners` for destructive ops unless the user explicitly requested writes.
