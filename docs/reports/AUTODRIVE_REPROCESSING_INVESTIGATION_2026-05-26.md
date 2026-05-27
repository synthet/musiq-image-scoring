# Auto-drive reprocessing investigation — 2026-05-26

**Reporter:** dmnsy (Claude Opus 4.7 assist)
**Trigger:** Run [#3245](http://127.0.0.1:7860/ui/runs/3245) — "Auto-drive queued this folder from the Runs buckets planner." Suspected re-processing of already-done images/phases.
**Status:** Fixed (2026-05-27). See [Implementation status](#implementation-status-2026-05-27) below. Operator summary: [AUTO_DRIVE_FIX_SUMMARY.md](AUTO_DRIVE_FIX_SUMMARY.md).

## TL;DR

Auto-drive's `awaiting_indexing` bucket re-queues every completed folder every time the planner runs, because the `executor_version_changed` check in `modules/phases_policy.py:74` produces false positives across **every** phase that has rows in `image_phase_status`:

- **metadata / culling** rows from old app versions persist `executor_version=NULL` → mismatches the registry's `"1.0.0"`.
- **scoring** rows persist the constant `SCORING_EXECUTOR_VERSION = "5.0.0"` (`modules/phases.py:62`), while the registry returns `scorer.shared_scorer.VERSION` (e.g. `topiq-nr-1`, `arniqa-1`) via `_get_scorer_version()` in `modules/phase_executors.py:115`. These two strings are never equal — every completed scoring row is permanently "stale" by definition.

Run 3245 burned ~379 s re-indexing 250 already-indexed images and had metadata/scoring/culling queued behind it. The only legitimate work was **bird_species** for 248/250 images + 1 with missing data.

## Evidence

### Job 3245 state (snapshot)

- `input_path`: `/mnt/d/Photos/Z6ii/28-400mm/2025/2025-03-16`
- `target_phases`: `[indexing, metadata, scoring, culling, keywords, bird_species]`
- `queue_payload.run_mode`: `process_stale_or_missing`
- `auto_drive_bucket`: `awaiting_indexing`
- `tool_id`: `runs_auto_drive`
- 250 images in scope (`image_id` 9100–9349)
- Phases at observation time:
  - indexing: completed (379.51 s, 250/250 processed, 0 skipped) ← **wasted work**
  - metadata: completed (0.23 s)
  - scoring: running
  - culling / keywords / bird_species: pending

### Pre-run DB state for the same 250 images

Aggregated counts from `image_phase_status` after the run started (indexing was already rewritten by the run; the rest reflect what existed before):

| `phase_id` | code | `status` | `executor_version` | n |
|---|---|---|---|---|
| 1 | indexing | done | `1.0.0` (rewritten this run) | 250 |
| 2 | metadata | done | **NULL** | 250 |
| 3 | scoring | done | `5.0.0` | 250 |
| 4 | culling | done | **NULL** | 250 |
| 5 | keywords | done | `1.0.0` | 250 |
| 6 | bird_species | done | `1.0.0` | **2** |

Spot-checked row (image 9100):

```
phase_id=1 status=done executor_version=1.0.0 app_version=7.24.0 finished_at=2026-05-27T02:46:02
phase_id=2 status=done executor_version=NULL  app_version=1.6.0  finished_at=NULL
phase_id=3 status=done executor_version=5.0.0 app_version=1.6.0  finished_at=NULL
phase_id=4 status=done executor_version=NULL  app_version=1.6.0  finished_at=NULL
phase_id=5 status=done executor_version=1.0.0 app_version=1.6.0  finished_at=2026-03-01T01:11:28
```

`app_version=1.6.0` confirms metadata/scoring/culling/keywords rows were written long ago by older code that did not persist `executor_version` consistently.

### Repair-plan summary from `queue_payload`

```json
"issue_counts": {
  "bird_species_needs_work": 249,
  "culling_needs_work": 250,
  "indexing_needs_work": 250,
  "keywords_needs_work": 0,
  "metadata_needs_work": 250,
  "scoring_needs_work": 250,
  "scoring_incomplete": 250,
  "bird_species_not_started": 248,
  "bird_species_missing_data": 1,
  "culling_stale_executor": 250,
  "indexing_stale_executor": 250,
  "metadata_stale_executor": 250,
  "scoring_stale_executor": 250
},
"issue_counts_by_reason": {
  "not_started": 248,
  "missing_data": 1,
  "stale_executor": 1000
}
```

`1000 = 4 phases × 250` → every completed-phase row counted as stale.

## Root cause walkthrough

### 1. `phases_policy.explain_phase_run_decision` — the version-mismatch trap

`modules/phases_policy.py:73-76`:

```python
# status == done (or unknown terminal): compare versions
if active_version and stored_version != active_version:
    decision["reason"] = "executor_version_changed"
    return decision
```

If `active_version` is set and not equal to `stored_version` (including `NULL`), the function **returns immediately** with `should_run=True`. The data-validation block below (lines 78–114, `is_image_scoring_complete` / `is_image_metadata_complete` / etc.) is unreachable in this branch. So even when the actual data is complete, the planner orders a rerun.

### 2. `_get_scorer_version()` returns the scorer-backend tag, not the persisted constant

`modules/phase_executors.py:115-132`:

```python
def _get_scorer_version(scoring_runner) -> str:
    try:
        if scoring_runner.shared_scorer and hasattr(scoring_runner.shared_scorer, 'VERSION'):
            return scoring_runner.shared_scorer.VERSION   # e.g. "topiq-nr-1"
    except Exception:
        pass
    try:
        from modules.phases import SCORING_EXECUTOR_VERSION
        return SCORING_EXECUTOR_VERSION                    # "5.0.0"
    except ImportError:
        pass
    return "1.0.0"
```

The `shared_scorer.VERSION` values found in the repo:

| Scorer | `VERSION` |
|---|---|
| `modules/arniqa.py` | `arniqa-1` / `f"{metric_name}-1"` |
| `modules/topiq.py` | `topiq-nr-1` |
| `modules/qpt_v2.py` | `qpt-v2-1` |
| `modules/cursor_scorer.py` | `cursor-judge-1` |
| `modules/claude_scorer.py` | `claude-judge-1` |
| `modules/engines/mock.py` | `mock-9.9.9` |
| `modules/engines/host.py` | `version or backend.VERSION or "host-0"` |

None match the canonical constant `SCORING_EXECUTOR_VERSION = "5.0.0"` (`modules/phases.py:62`), which other paths persist as the scoring `executor_version`. Result: `"5.0.0" != "topiq-nr-1"` every time the planner asks.

### 3. Metadata / culling never persisted `executor_version` in older runs

The registry hard-codes `"1.0.0"` for both (`modules/phase_executors.py:54, 79`). For any row with `executor_version=NULL`, `NULL != "1.0.0"` → `executor_version_changed`.

### 4. Bucket selection compounds the issue

`runs_autodrive._build_bucket_from_summary` (`modules/runs_autodrive.py:383`) selects `awaiting_indexing` based on per-folder phase summary completeness. The 250 indexing rows are `status=done`, so the summary should report indexing complete — but the bucket still says "awaiting_indexing". Either (a) the summary aggregation is reading something other than `image_phase_status.status='done'`, or (b) bird_species's 248 not-started rows are leaking into the indexing-completion calculation. Worth verifying as a follow-up; the planner bug above is independently sufficient to explain the reprocessing.

## Impact

- Every auto-drive cycle re-queues all previously-completed folders with old `app_version` rows.
- Per-folder cost: ~6 minutes of wasted indexing alone (379 s for 250 images), plus metadata/scoring/culling time. Across the photo library this is hours of needless GPU/CPU work per cycle.
- Risk of clobbering existing scoring data with a different model's outputs when the rerun completes.
- `runs_auto_drive` health/percent metrics are pessimistic (showing 0% on actually-complete folders).

## Implementation status (2026-05-27)

| Recommendation | Status | Notes |
|----------------|--------|--------|
| 1. NULL `executor_version` → trust data validation | **Done** | `modules/phases_policy.py` — version compare requires truthy `stored_version`. |
| 2. Single scoring executor version authority | **Done** | Registry + `pipeline.py` IPS writes use `SCORING_EXECUTOR_VERSION` (`5.0.0`); `_get_scorer_version()` no longer returns `shared_scorer.VERSION`. |
| 3. Invert gate (data check before version bump) | Deferred | Rec #1 achieves same outcome for legacy NULL rows; explicit back-fill optional later. |
| 4. Folder phase summary audit | **Partial** | Dirty/missing cache refresh in `build_folder_buckets`; see runs_autodrive changes in fix summary. |
| 5. Regression tests | **Done** | `tests/test_phases_policy.py` (NULL metadata, canonical scoring); `tests/test_runs_autodrive.py` (buckets + enqueue). |

**Also shipped:** JIT-aligned auto-drive enqueue (`phases_with_work_from_repair_plan`), folder-bucket cache refresh, Runs UI planner queue panel, `scripts/diagnostics/capture_run_planner_snapshot.py`.

**After deploy:** Restart WebUI; `POST /api/runs/plan/preview` on a folder should show near-empty `stage_queues` for completed work (except real gaps e.g. bird_species).

---

## Recommendations (ordered by smallness) — original spec

1. **Treat `stored_version=NULL` as "unknown — trust the data"** (smallest patch, ~3 lines in `modules/phases_policy.py:74`):

   ```python
   if active_version and stored_version and stored_version != active_version:
       decision["reason"] = "executor_version_changed"
       return decision
   ```

   Falls through to the per-phase `is_image_*_complete()` check, which is the desired behavior for legacy rows. Removes metadata/culling false positives and any other pre-versioning rows.

2. **Pick one authority for the scoring executor version.** Either:
   - persist `SCORING_EXECUTOR_VERSION` (`"5.0.0"`) everywhere and make `_get_scorer_version()` return the same constant; or
   - persist `scorer.VERSION` everywhere and bump the constant only on algorithm changes.

   Today `modules/pipeline.py:221, 233, 305, 614, 704` writes `self.scorer.VERSION`, but other code paths and existing DB rows hold `"5.0.0"`. Pick one and migrate.

3. **Invert the gate for completed work.** When `status == done`, run the data-validation checks first; only escalate to "rerun" on `executor_version_changed` if the data is *also* incomplete. Otherwise log a one-time `back-fill executor_version on completed row` and skip.

4. **Audit the folder phase summary** used by `runs_autodrive._build_bucket_from_summary` to confirm an all-done folder reports indexing as complete; if not, the bucket classifier needs a separate fix.

5. **Add a regression test:** seed `image_phase_status` rows with `status='done', executor_version=NULL` for metadata/culling and `executor_version='5.0.0'` for scoring; assert `plan_scope` returns empty `stage_queues` for those phases.

## Files referenced

- `modules/phases_policy.py:28-118` — `explain_phase_run_decision`, the central gate.
- `modules/phases_policy.py:74` — the broken version-mismatch branch.
- `modules/run_phase_planner.py:40-56` — `_reason_bucket` mapping (`executor_version_changed` → `stale_executor`).
- `modules/run_phase_planner.py:84-143` — `plan_scope` (drives auto-drive).
- `modules/phase_executors.py:34-110` — registry version assignments.
- `modules/phase_executors.py:115-132` — `_get_scorer_version`.
- `modules/phases.py:62` — `SCORING_EXECUTOR_VERSION = "5.0.0"`.
- `modules/runs_autodrive.py:383-470` — bucket classifier.
- `modules/pipeline.py:215-307` — scoring per-image policy gate and persistence.

## Investigation method (for repro)

1. `get_run_diagnostics(run_id=3245)` → confirmed `images_processed=250`, `run_mode=process_stale_or_missing`, all phase indexing done.
2. `get_job_phases(3245)` → indexing+metadata completed, scoring running, others pending.
3. `get_job_details(3245)` → extracted `queue_payload.repair_plan_summary` showing `stale_executor: 1000`.
4. `execute_sql` on `image_phase_status` for `image_id BETWEEN 9100 AND 9349` grouped by `(phase_id, status, executor_version)` — confirmed all phases already `done`.
5. Read `phases_policy.py`, `run_phase_planner.py`, `phase_executors.py`, `pipeline.py`, `runs_autodrive.py` to localize the version-comparison logic.
