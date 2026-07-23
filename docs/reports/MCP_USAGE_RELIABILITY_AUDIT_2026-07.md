---
type: Report
title: MCP tools usage and reliability audit — July 2026
description: Transcript usage heatmap for compact is-be-mcp / is-ui-mcp actions, live probe matrix, and fix for Python compact-worker JSON datetime crashes.
resource: docs/reports/MCP_USAGE_RELIABILITY_AUDIT_2026-07.md
tags: [docs, reports, mcp, agents, audit]
timestamp: 2026-07-22T00:00:00Z
okf_version: 0.1
---

# MCP tools usage and reliability audit — July 2026

Point-in-time review of compact MCP surfaces (`is-be-mcp`, `is-ui-mcp`) against recent Cursor agent transcripts and live `dispatch` probes. Contract: [MCP_SEARCH_DISPATCH.md](../technical/MCP_SEARCH_DISPATCH.md).

## Verdict

Compact MCP **works for triage** after a serialization fix. Before the fix, several high-value DB actions (`diagnostics.get_error_summary`, `jobs.get_recent_jobs`, `data.query_images`) crashed the long-lived WSL Python worker with `TypeError: Object of type datetime is not JSON serializable`, which Cursor surfaced as `Python compact worker exited (code=1)`. Agents therefore over-relied on `data.execute_sql` and skipped `search`.

## Inventory (attached in this workspace)

| Surface | Tools | Actions |
|---------|-------|---------|
| **is-be-mcp** | `search`, `dispatch`, `sse_status` | 26 compact actions in `mcp/action_registry.json` + Playwright browser actions in `mcp/actions/playwright_registry.json` |
| **is-ui-mcp** | `search`, `dispatch`, `sse_status` | 20 actions in gallery `mcp-server/action_registry.json` |
| Also attached | fff-be, fff-gallery, user-github, user-subagent-orchestrator | file search / GitHub / CLI reviews |

## Transcript usage heatmap

Source: 200 most recent agent transcript JSONL files under the backend Cursor project (aggregate `action_id` / `toolName` counts only; no conversation text). Gallery-only transcript tree was not present as a separate folder.

| Metric | Value |
|--------|------:|
| Transcripts with MCP signals | 59 |
| `dispatch` toolName | 226 |
| `search` toolName | 18 |
| search / dispatch ratio | 0.08 |
| Dominant server | `is-be-mcp` (243 refs) |
| Gallery MCP | `is-ui-mcp` (12 refs) |

### Top known `action_id` mentions

| Mentions | action_id |
|---------:|-----------|
| 136 | `data.execute_sql` |
| 10 | `jobs.get_job_details` |
| 7 | `jobs.get_run_diagnostics` |
| 7 | `diagnostics.get_error_summary` |
| 7 | `jobs.get_recent_jobs` |
| 6 | `data.get_embedding_stats` |
| 6 | `jobs.get_runner_status` |
| 5 | `config.get_config` |
| 4 | `local.gallery_status` |
| 4 | `diagnostics.check_database_health` |

### Unused or near-zero (notable)

- **Backend unused in sample:** `diagnostics.run_doctor`, `diagnostics.verify_environment`, `diagnostics.get_model_status`, `logs.read_debug_log`, `logs.get_server_log_tail`, `support.export_debug_bundle`, all `browser.*`.
- **Gallery near-zero:** most `api.*` / `live.*` / local helpers except occasional `local.gallery_status`.
- **Non-registry IDs agents invented:** `jobs.get_job_phases`, `jobs.get_pipeline_stats`, `jobs.get_job_execution_report`, bare `execute_sql` (legacy name).

### Agent anti-patterns

1. **Skip `search`** — dispatch by memory; ratio ~0.08.
2. **SQL-first** — `data.execute_sql` dominates; named diagnostics underused for common triage.
3. **Invent action_ids** from AGENTS.md legacy inventory instead of registry / `search` suggestions.
4. **Legacy residue** — raw tool names (`get_recent_jobs`, `get_stacks_summary`) still appear as `toolName` in older turns.

## Live reliability

### Root cause (fixed)

[`scripts/mcp/compact_worker.py`](../../scripts/mcp/compact_worker.py) wrote responses with bare `json.dumps`. Postgres-backed handlers return `datetime` (and sometimes `Decimal` / `UUID`) inside envelopes. Serialization raised **outside** the request try/except → process exit 1 → Node [`pythonBridge.ts`](../../mcp-server/src/utils/pythonBridge.ts) rejected pending calls.

**Fix:** `dumps_response()` with `_json_default` (datetime/date/time/Decimal/UUID/Path/bytes) plus a last-resort `serialization_error` envelope so the worker stays alive. Tests in [`tests/test_mcp_compact_worker.py`](../../tests/test_mcp_compact_worker.py).

### Probe matrix (post-fix)

All 25 read-only compact backend actions probed via one-shot WSL worker invocations: **25 success, 0 crashes**. Skipped side-effect `support.export_debug_bundle` and Playwright browser actions (not exercised in transcripts).

Also verified through Cursor `is-be-mcp` after the fix: `diagnostics.get_error_summary` and `jobs.get_recent_jobs` return `status: success`. Gallery: `local.gallery_status` / `local.get_system_stats` / `api.api_health` succeed; `api.api_probe` correctly returns `validation_error` without required `path`; `is-ui-live` SSE was down (Electron not running).

| action_id | Live status |
|-----------|-------------|
| All 25 compact read-only backend actions listed in probe scratch | success |
| `support.export_debug_bundle` | not probed (confirmed side effect) |
| `browser.*` | not probed (unused in transcripts) |

## Recommendations

1. Prefer `search` → `dispatch` for unfamiliar intents; prefer named diagnostics over ad-hoc SQL for scoring/job triage.
2. Optional follow-up: expose compact wrappers for actions agents invent (`jobs.get_job_phases`, `jobs.get_job_execution_report`) via overlay regeneration — not done in this pass.
3. Playwright browser actions remain available but unused; no promotion needed unless product wants UI automation via MCP.

## Related

- Skill: [image-scoring-mcp](../../.cursor/skills/image-scoring-mcp/SKILL.md)
- Smoke: [`scripts/smoke_mcp_compact.py`](../../scripts/smoke_mcp_compact.py)
