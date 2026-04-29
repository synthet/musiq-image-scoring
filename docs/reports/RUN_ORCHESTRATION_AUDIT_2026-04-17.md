# Run Orchestration Audit — 2026-04-17

Snapshot of bugs, defects, and gaps in job/run orchestration derived from `webui.log`, the PostgreSQL `jobs` / `job_phases` / `image_phase_status` tables, and the current codebase.

**Data sources:** MCP tools (`get_error_summary`, `get_runner_status`, `get_pipeline_stats`, `check_database_health`, `get_server_log_tail`, `execute_sql`), `modules/scoring.py`, `modules/job_dispatcher.py`, `scripts/python/run_all_musiq_models.py`.

---

## 1. Code bugs / regressions

### 1.1 `MultiModelMUSIQ.load_model` AttributeError (6 recent failures)

- **Symptom:** `Error loading models: 'MultiModelMUSIQ' object has no attribute 'load_model'` — jobs 1239/1242/1244/1245 (Apr 16 04:49–05:06) all on `/mnt/d/Photos/Z8/180-600mm/2026/2026-04-09`.
- **Reality:** `scripts/python/run_all_musiq_models.py:867` defines `load_model`. Same import path succeeds for other runs.
- **Suspect:** `modules/scoring.py:27` sets `MultiModelMUSIQ = None` when import fails; a partial / swallowed import on some cold starts leaves `MultiModelMUSIQ` bound to a stub that lacks `load_model`, yet is not `None` (so the `_musiq_import_error` guard at `modules/scoring.py:126` is bypassed). Intermittent; likely an import-order race.
- **Fix direction:** Harden the import guard — verify `hasattr(MultiModelMUSIQ, 'load_model')` before instantiation, or surface the real `_musiq_import_error` consistently.

### 1.2 Missing `modules.db` attributes (historic + current)

- 11 tool jobs failed Apr 13–14 with `module 'modules.db' has no attribute 'update_job_phase_state' | 'log_job_event' | 'update_job_progress'`.
- `update_job_progress` still called from `modules/maintenance_runner.py` (7 sites). The function now exists at `modules/db.py:4261`, so currently safe — but the regression pattern (callers outpacing the `db.py` facade) is recurring.
- **Also live:** MCP tool `get_stale_running_phase_status` errors with `module 'modules.db' has no attribute 'list_stale_running_image_phase_rows'` — same drift.
- **Fix direction:** Add a contract test that imports `modules.db` and asserts every symbol used by runners / MCP tools resolves.

### 1.3 Dispatcher treats runner-busy as terminal failure

- 18 jobs failed with `Runner 'selection_runner' returned: Error: Already running.` Source: `modules/job_dispatcher.py:218` (`return False, f"Runner '{runner_name}' returned: {result}"`).
- All 7 runners (`scoring`, `tagging`, `clustering`, `selection`, `indexing`, `metadata`, `maintenance`, `bird_species`) return the same string on collision (grepped).
- **Fix direction:** Detect the `"Already running"` marker and re-queue instead of failing the job, or block dispatch until the runner is idle.

---

## 2. Orchestration state drift

### 2.1 `image_phase_status` rows stuck in `running`

- **137** rows with `status='running'`, **75** older than 1 hour. Folder badges will keep showing "running" after crashes.
- No automated sweeper to demote stale rows to `failed`.
- The tool meant to surface this (`get_stale_running_phase_status` → `list_stale_running_image_phase_rows`) is itself broken (§1.2).

### 2.2 Stuck `jobs.status='running'` rows

- Jobs **1247** (null log) and **1248** (log shows `[indexing] Done.`) created 00:26–00:27 on 2026-04-17, still `running` at audit time. The currently active scoring runner is processing a **different path**. These rows transitioned phase but the job close path didn't execute.
- **Fix direction:** Ensure `db.update_job_status` runs in a `finally` around the runner thread; add a stale-job reaper.

### 2.3 40 jobs closed by maintenance as "Stale"

- `\nStale job closed by maintenance.` is the most common failure log (40 occurrences). Indicates repeated unclean shutdowns / crashes leaving orphans that only the maintenance sweep can clean.

---

## 3. Input validation gaps

### 3.1 `Path not found` after job creation (37+ jobs)

- 37 scoring jobs failed with `Runner 'scoring_runner' returned: Path not found` — `modules/scoring.py:86`.
- Many indexing jobs log `[indexing] Input path not found: /mnt/...`.
- Path existence is checked inside the runner, **after** `create_job` has persisted the record. The job is accepted, dequeued, then immediately fails.
- **Fix direction:** Validate `os.path.exists(convert_path_to_local(input_path))` at the API layer (`modules/api.py` already does this for some endpoints — `:1989`, `:2237`, `:2442`, `:4595` — but not consistently for scoring/indexing/selection create-paths).

---

## 4. Data quality / schema

### 4.1 `cancelled` vs `canceled` spelling split

- `jobs.status`: `cancelled` × 37, `canceled` × 21 — both in use.
- `job_phases.state`: only `canceled` × 17.
- **Risk:** Filters / dashboards keyed on one spelling silently miss the other.
- **Fix direction:** One-shot UPDATE to normalize, add CHECK constraint, grep callers.

### 4.2 Naming drift between phase tables

- `image_phase_status.status` vs `job_phases.state` for the same conceptual field.
- Cognitive trap for anyone writing cross-table queries (verified — two MCP SQL calls failed during this audit on the wrong column name).

### 4.3 Stack cleanup never runs

- **12,363** empty stacks (55% of `stacks`), **1,523** singleton stacks, out of 22,387 total. Only 10,024 are actually referenced by any image.
- Culling / clustering does not clean up after itself; no FK cascade on `images.stack_id` dereference.

### 4.4 Score coverage gaps

- Missing `general_score` × 4,860; `technical_score` × 4,859; `spaq` × 4,859; `ava` × 4,858; `liqe` × 4,859; `koniq` × 16,803; `paq2piq` × 16,803.
- Orchestrator doesn't re-enqueue images with partial model coverage.

### 4.5 74 folders with zero images

- Surfaced by `check_database_health`; never cleaned.

---

## 5. Runtime / performance

### 5.1 Event loop stalls driven by MCP SSE

- `webui.log` at audit time:
  - `[SLOW REQUEST] GET /mcp/sse -> 200 in 147169ms (VERY SLOW, loop_lag=1ms)`
  - `[SLOW REQUEST] GET /mcp/sse -> 200 in 15104ms`
  - `[EVENT LOOP BLOCKED] Lag: 5014ms`
  - Follow-on `POST /mcp/messages/` calls tagged `loop_lag=5014ms`.
- While SSE is held, **every** async caller (dispatcher heartbeat, API clients) sees latency.
- **Fix direction:** Run MCP SSE on its own executor / thread pool, or offload the blocking work.

---

## 6. Summary — suggested priorities

| # | Issue | Blast radius |
|---|-------|--------------|
| 1 | `MultiModelMUSIQ.load_model` import regression (§1.1) | Highest user-visible failure rate |
| 2 | Stuck `running` rows + missing sweeper (§2.1, §2.2, §1.2) | Misleading UI, unreliable resume |
| 3 | Dispatcher fails instead of re-queuing on runner busy (§1.3) | 18+ avoidable failures |
| 4 | API-side path validation (§3.1) | 37+ avoidable failures |
| 5 | `cancelled/canceled` normalization (§4.1) | Silent dashboard under-counting |
| 6 | MCP SSE event-loop stalls (§5.1) | Cascade latency across the stack |
| 7 | Empty/singleton stack cleanup (§4.3) | DB bloat, clustering correctness |

---

## Cross-references

- Pipeline phases & statuses: [../architecture/system-overview.md](../architecture/system-overview.md)
- DB schema: [../technical/DB_SCHEMA.md](../technical/DB_SCHEMA.md)
- Prior phase/stack investigation: [CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md](CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md)
- Backlog: [../../TODO.md](../../TODO.md)
