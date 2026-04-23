# RCA — Runs/DB/Logs audit (2026-04-22)

Root-cause analysis for the defects surfaced in the runs/DB/logs review. Severity tags match the audit plan.

---

## [HIGH-1] `heal_workflow_scoring` infinite no-op loop

### Symptom
Same folders (e.g. `Z8/105mm/2026/2026-03-12`, `Z8/180-600mm/2026/2026-03-14`) complete 6-7 consecutive scoring jobs with `images_processed=0` and log `"Skipping fully scored folder …"` / `"No images found."` The healer re-enqueues them every ~24 min.

### Root cause: two conflicting definitions of "fully scored"

1. **Healer side** — [modules/db_legacy.py:7333](modules/db_legacy.py#L7333) `_incomplete_images_where_sql` considers an image scoring-incomplete if **any** of these is missing:
   - `score`, `rating`, `label` (user-facing aggregate fields)
   - `score_general`, `score_technical`
   - `score_spaq`, `score_ava`, `score_liqe`

2. **Engine side** — [modules/engine.py:103](modules/engine.py#L103) short-circuits any folder where `db.is_folder_scored()` returns True. That flag (`folders.is_fully_scored`) is set by [modules/db_legacy.py:3855](modules/db_legacy.py#L3855) `check_and_update_folder_status`, which **only** checks `score_general > 0`:
   ```python
   scored_files = {row['file_name'] for row in rows
                   if row['score_general'] and row['score_general'] > 0}
   ```

### Trigger path
1. Healer (`workflow_healing.heal_phase_data`, [modules/workflow_healing.py:47](modules/workflow_healing.py#L47)) picks up images that have `score_general` but a missing `rating`, `label`, or any of the secondary model scores.
2. It enqueues a scoring run with `run_mode="process_unprocessed_or_empty"`, which sets `skip_existing=True` ([modules/run_modes.py:14-21](modules/run_modes.py#L14-L21)).
3. `BatchScoringProcessor.process` ([modules/engine.py:101-108](modules/engine.py#L101-L108)) walks the folder, sees `is_folder_scored=True`, skips **without** resetting the folder flag or the image phase statuses.
4. Job completes as success → healer loop fires again next cycle → 1–3 repeat.

### Why the queue grows forever
- Healer's own query to exclude folders under active run ([workflow_healing.py:101](modules/workflow_healing.py#L101)) looks only at `running`/`queued` jobs. It doesn't check "did this folder just complete a no-op heal run." Every idle window re-picks the same folders.
- The audit data confirms saturation: for `Z8/105mm/2026/2026-03-19` all 6 runs and for `Z8/105mm/2026/2026-03-12` all 7 runs are no-ops.

### Fix options
- **Narrow**: make `check_and_update_folder_status` validate the same columns `_incomplete_images_where_sql` does. Then `is_fully_scored=1` implies healer finds nothing.
- **Broader / safer**: healer should pass `skip_existing=False` when run_mode is a healing mode (or switch to `validate_and_repair` which already sets `skip_existing=False`, but api caller is forcing `process_unprocessed_or_empty`). Find the caller in [modules/api.py:6189](modules/api.py#L6189) and change the default.
- **Belt-and-braces**: after a no-op heal run (`images_processed=0` but `false_positive_ids > 0`), reset `folders.is_fully_scored=0` for the scope so the next pass actually runs scoring.

---

## [HIGH-2] DB facade missing `update_job_phase_state` / `log_job_event`

### Symptom
5 failed jobs: `module 'modules.db' has no attribute 'update_job_phase_state'`; 3 failed jobs for `log_job_event`.

### Root cause
Grep finds **zero** call sites in the current tree (only a doc reference in `docs/reports/RUN_ORCHESTRATION_AUDIT_2026-04-17.md`). The failures are historical — callers were deleted before the db refactor (commit `a083cf5`) moved the monolith to `db_legacy.py`.

### Assessment
**Already fixed** by deletion of the callers. No action beyond confirming the failed jobs are dated before the fix (the 8 failures predate current HEAD). Skip unless re-occurs.

---

## [HIGH-3] `'MultiModelMUSIQ' object has no attribute 'load_model'`

### Symptom
6 jobs on 2026-04-16 failed instantly during model initialization.

### Current state
`MultiModelMUSIQ` at [scripts/python/run_all_musiq_models.py:58](scripts/python/run_all_musiq_models.py#L58) has `def load_model(self, model_name: str)` at [line 867](scripts/python/run_all_musiq_models.py#L867). Callers at [modules/scoring.py:171, 504, 766](modules/scoring.py#L171) invoke it correctly.

### Root cause (inferred)
The method was absent on 2026-04-16 and added afterwards. The scoring module has a module-load-time circuit breaker ([modules/scoring.py:137-194](modules/scoring.py#L137-L194)) that captures import failures in `_musiq_import_error`, but the surfaced error path is an `AttributeError` at call time, meaning the class imported successfully but its API was incomplete.

### Assessment
**Already fixed** (method exists in HEAD). Monitor; no action unless it returns.

---

## [MED-4] "Path not found" — 37 failed runs

### Symptom
Healer enqueues indexing/scoring for deleted folders (e.g. `Z6ii/28-400mm/2025/2025-10-27`).

### Root cause
Healer's folder query ([workflow_healing.py:74-94](modules/workflow_healing.py#L74-L94)) joins `images → folders` by `folder_id` — purely DB-side. There is no disk-existence check before enqueue. When the user deletes a folder on disk, the `folders` row and its `images` rows persist (no cascade), so the healer keeps selecting them.

### Fix
- Pre-enqueue: `os.path.isdir(folder_path)` in `_enqueue_heal_run` before `db.enqueue_job`; skip silently if the path is gone.
- Background: schedule `pruneMissing` (already exists, ran once) on a cron — daily is enough for a photo library.

---

## [MED-5] `selection_runner returned: Error: Already running.` (18×)

### Likely root cause
Selection runner uses an in-process `is_running` flag (pattern seen in all runners in `get_pipeline_stats`). On crash/cancellation the `finally` block does not clear it, or the dispatcher sets the flag but a worker exception propagates past the cleanup. Without reading the runner, the mitigation is:

- Wrap the runner entrypoint in `try/finally: self.is_running = False`.
- Add a watchdog that clears the flag if no progress for N minutes (same pattern used for stale-job sweep).

Needs code inspection in `modules/selection.py` to confirm before patching.

---

## [MED-6] 40 jobs "Stale job closed by maintenance"

### Root cause (hypothesis)
Maintenance sweep is the only path that reconciles jobs whose runner died without writing `finished_at`. That works, but it's downstream of the real bug — the runner lost its exception-safe cleanup. Correlate with HIGH-3 date (2026-04-16) and the selection lock issue; likely the same underlying missing `finally`.

### Fix
Same remedy as #5 — enforce `try/finally` discipline in every runner's main loop. Independently, maintenance stale-close should stay as safety net.

---

## [MED-7] KoniQ/PAQ2PiQ coverage gap (17,612 images)

### Root cause (confirmed in code)
[modules/db_legacy.py:7341-7342](modules/db_legacy.py#L7341-L7342):

```python
# Only check for models that are consistently used in the default pipeline.
# koniq and paq2piq are excluded as they are optional/not currently loaded by default.
models = ['spaq', 'ava', 'liqe']
```

The completeness check **intentionally** excludes `koniq` and `paq2piq`, so images with NULL in those columns are never flagged incomplete — and never healed. Meanwhile [modules/scoring.py:167](modules/scoring.py#L167) loads only `['spaq', 'ava']`. The 17,612 gap is expected given current config.

### Assessment
Not a bug — a **config/design gap**. If KoniQ/PAQ2PiQ scores are wanted: (a) add them to `musiq_models` in `scoring.py:167`, (b) include them in `_incomplete_images_where_sql`, (c) one-off backfill. If not wanted: drop the columns or explicitly document them as optional. Decide first; don't "fix" until the product intent is clear.

---

## [MED-8] Folder "fully scored" flag out of sync with per-image scores

### Root cause
Same as HIGH-1 root cause #2. `check_and_update_folder_status` uses a narrower definition than `_incomplete_images_where_sql`. Fixing HIGH-1 fixes this.

---

## [LOW-9] 12,364 orphaned stacks

### Root cause (hypothesis)
Image delete path doesn't cascade to stacks. When an image is removed (file pruned or re-indexed into a different stack), the stack membership row goes but the stack row stays. Over months of re-clustering this accumulates.

### Fix
- Periodic sweep: `DELETE FROM stacks WHERE NOT EXISTS (SELECT 1 FROM images WHERE stack_id = stacks.id)` — safe and cheap.
- Better: cascade delete on membership change in `modules/clustering.py`.

---

## [LOW-10] `/api/health` timed out at 10s

### Likely root cause
Health handler is probably grabbing the same DB connection pool or sync lock the scoring dispatcher is saturating. Health must be O(1) and lock-free. Handler lives in `modules/api.py`.

---

## [LOW-11] `read_debug_log` path

`modules/mcp_server.py` returns `/app/.cursor/debug.log` — Linux-container path on a Windows host. Trivial fix: resolve via repo-relative `BASE_DIR / ".cursor/debug.log"` (and create on startup).

---

## Recommended execution order

1. Patch `check_and_update_folder_status` to match `_incomplete_images_where_sql` (kills HIGH-1 and MED-8 in one go).
2. Add disk-existence pre-check in `_enqueue_heal_run` (MED-4).
3. Audit all runner main loops for `try/finally` cleanup (MED-5, MED-6).
4. Decide KoniQ/PAQ2PiQ: add to default scoring OR remove from schema (MED-7).
5. Periodic orphan-stack sweep (LOW-9).
6. Fix `/api/health` handler (LOW-10).
7. Path in `read_debug_log` (LOW-11).
