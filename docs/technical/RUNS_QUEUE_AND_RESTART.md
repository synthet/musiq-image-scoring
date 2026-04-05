# Runs queue and application restart

How batch **runs** (rows in the `jobs` table) behave when the WebUI process stops and starts again.

## Where the queue lives

Queued work is **not** held only in memory. It is stored in Firebird in the **`jobs`** table (`queue_position`, `enqueued_at`, `status`, `queue_payload`, priority, etc.).

- **[`GET /api/queue`](../../modules/api.py)** (see `get_run_queue`) lists queued jobs via [`db.get_queued_jobs`](../../modules/db.py). With the default `include_related=False`, that path returns rows with **`status = 'queued'`** only.
- **[`JobDispatcher`](../../modules/job_dispatcher.py)** polls [`db.dequeue_next_job()`](../../modules/db.py), which atomically picks the next row with `status = 'queued'` and `cancel_requested = 0`, ordered by priority, `queue_position`, `enqueued_at`, and `id`, then sets it to `running`.

## Startup order

In [`webui.py`](../../webui.py), `app_module.create_ui()` runs **before** [`setup_server_endpoints`](../../modules/ui/app.py), which calls [`api.set_runners`](../../modules/api.py) and starts **`_job_dispatcher.start()`**.

Inside `create_ui`, [`_init_webui_engines`](../../modules/ui/app.py) runs `db.init_db()` then [`PipelineOrchestrator.recover_interrupted_jobs`](../../modules/pipeline_orchestrator.py). Recovery therefore runs **while the dispatcher thread is still stopped**, so stale `running` rows are not raced with a live dequeue.

## Status transitions on restart

| Status before restart | After init |
|----------------------|------------|
| **`queued`** | Unchanged. Still eligible for `dequeue_next_job` in sort order. |
| **`paused`** | Unchanged. **Not** dequeued (`dequeue_next_job` only selects `queued`). Resume explicitly if needed. |
| **`running`** | **All** such rows are updated by [`db.recover_running_jobs`](../../modules/db.py) to **`interrupted`** (with `runner_state` / `completed_at` set). They are **not** automatically re-queued. |
| **`failed`**, **`completed`**, **`cancelled`** | Unchanged. Not part of the dequeue queue. |

Recovery is invoked from [`modules/ui/app.py`](../../modules/ui/app.py); it calls `recover_running_jobs(mark_as="interrupted")` for **every** job still marked `running`, not only pipeline jobs.

## Pipeline auto-resume

After recovery, the orchestrator may look up interrupted **pipeline** jobs (`job_type = 'pipeline'`). If config **`pipeline.auto_resume_interrupted`** is true and no orchestrator run is already active, it calls [`start(folder)`](../../modules/pipeline_orchestrator.py) for that folder — a **new** run while the historical interrupted row remains.

## UI and API

- The React **Runs** page ([`frontend/src/pages/RunsPage.tsx`](../../frontend/src/pages/RunsPage.tsx)) treats **`interrupted`** as **history**.
- **[`POST /api/runs/{run_id}/retry`](../../modules/api.py)** enqueues a **new** job from an existing record; [`RunCard`](../../frontend/src/components/runs/RunCard.tsx) exposes Retry for **`failed`** and **`interrupted`**.

## Restart recovery: `jobs` + `job_phases`

[`recover_running_jobs`](../../modules/db.py) runs during WebUI init (see below). It updates **both** the job row and any **in-flight** phase rows for those jobs so the UI does not leave a stage stuck on “running” after a crash.

### Before the fix (conceptual)

If the server died while Run #305 was active:

- `jobs`: `id=305`, `status='running'`
- `job_phases`: e.g. `job_id=305`, `phase_code='culling'`, `state='running'`

After restart, only `jobs` was set to `interrupted`. **`job_phases` could stay `running`** → run-level badge “Interrupted” but workflow still showed a spinner on that stage.

### After the fix

Same crash state; on restart `recover_running_jobs('interrupted')`:

1. `SELECT id FROM jobs WHERE status = 'running'` → e.g. `[305]`
2. `UPDATE jobs SET status = ?, completed_at = ?, runner_state = ? WHERE status = 'running'`
3. `UPDATE job_phases SET state = ?, completed_at = ? WHERE job_id IN (…) AND state = 'running'`

Only phases that were **`running`** for those job IDs are updated. Completed/pending/failed phases on the same run (and all rows on other jobs) are unchanged.

### What stays untouched

| Example | Result |
|---------|--------|
| Run #300 already `completed` | Not selected; phases stay as-is |
| Run #306 `queued`, phases `queued` | Not selected; dispatcher picks up the job later |
| Run #305 interrupted: earlier phases `completed` | Still `completed`; only the former `running` phase becomes `interrupted` |

### Code path

`webui.py` `main()` → `create_ui()` → `_init_webui_engines()` → `db.init_db()` then `orchestrator.recover_interrupted_jobs()` → **`db.recover_running_jobs('interrupted')`** → optional pipeline auto-resume → later `api.set_runners()` → `_job_dispatcher.start()`.

## Per-image phase status (`image_phase_status`)

`recover_running_jobs` still does **not** infer per-image progress from `jobs` alone, but after it marks runs interrupted it calls **`reconcile_stale_running_phases_for_jobs`** so rows still **`running`** for those job ids are flipped to **`failed`** with `last_error` `stale_running_reconciled:job_interrupted`. That prevents folder phase rollups from staying stuck on “running” after a crash.

On WebUI init, **`reconcile_stale_running_phases_for_terminal_jobs`** (see [`modules/db.py`](../../modules/db.py)) also fixes **`running`** rows whose **`jobs`** row is already terminal (completed/failed/canceled/interrupted). Count is surfaced under `job_recovery.reconciled_terminal_job_phase_rows` in config loaded from [`modules/ui/app.py`](../../modules/ui/app.py).

When a job reaches a terminal status via **`update_job_status`**, the same reconcile runs for that **`job_id`** so user-stopped batches (e.g. metadata runner `stop` after setting **`running`** on an image) do not leave stale **`running`** rows.

Optional: set **`processing.strict_job_completion_verify`** to **`true`** in `config.json` to fail single-phase jobs at completion time when **`queue_payload.resolved_image_ids`** is set and any listed image is not terminal for that phase (guards “green run” vs incomplete per-image state).

Diagnostics: MCP **`get_stale_running_phase_status`** lists long-**`running`** `image_phase_status` rows; **`check_database_health`** warns when the count > 0 (older than 1 hour).

### Runner exit audit (brief)

| Runner | `update_job_status` on success path | Notes |
|--------|-------------------------------------|--------|
| [`IndexingRunner`](../../modules/indexing_runner.py) | `completed` / `failed` | User **stop** still ends with **`completed`** (same as metadata). |
| [`MetadataRunner`](../../modules/metadata_runner.py) | `completed` / `failed` | Mid-loop **stop** can leave last image **`running`** until job-level reconcile. |
| [`ScoringRunner`](../../modules/scoring.py) | `completed` / `failed` | Multiple entry paths set terminal status. |
| [`TaggingRunner`](../../modules/tagging.py) | `completed` / `failed` | |
| [`SelectionRunner`](../../modules/selection_runner.py) / clustering | `completed` via `_complete_phase_and_advance` | Uses **`set_job_phase_state`** for culling. |
| [`ClusteringRunner`](../../modules/clustering.py) | `completed` / `failed` | |

## Out of scope for this recovery

- FastAPI **`lifespan`** in [`webui.py`](../../webui.py) (event loop / loop monitor only) does **not** modify `jobs`.

## Related code

| Area | File |
|------|------|
| WebUI init + recovery call | [`modules/ui/app.py`](../../modules/ui/app.py) |
| Stale `running` → `interrupted` | [`modules/db.py`](../../modules/db.py) — `recover_running_jobs` (updates matching `job_phases` rows), `dequeue_next_job`, `get_queued_jobs`, `enqueue_job`; `set_job_phase_state` allows `running` → `interrupted` |
| Background dequeue | [`modules/job_dispatcher.py`](../../modules/job_dispatcher.py) |
| Pipeline recovery / auto-resume | [`modules/pipeline_orchestrator.py`](../../modules/pipeline_orchestrator.py) |
| Dispatcher start | [`modules/api.py`](../../modules/api.py) — `set_runners` |
