# Auto-drive reprocessing — investigation summary

**Date:** 2026-05-27  
**Canonical detail:** [AUTO_DRIVE_FIX_SUMMARY.md](AUTO_DRIVE_FIX_SUMMARY.md) · [AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md](AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md)

## Context

Auto-drive jobs such as run **3245** (`/ui/runs/3245`) showed:

> *Auto-drive queued this folder from the Runs buckets planner.*

Concern: folders that looked fully processed were queued for six pipeline stages (~250 images each) while `image_phase_status` was already `done` for most phases.

**Example folder:** `/mnt/d/Photos/Z6ii/28-400mm/2025/2025-03-16`  
**Legitimate gap:** mostly `bird_species` (~248 images); false positives were driven by `stale_executor` (~4× image count).

## Root causes

1. **Planner `executor_version_changed`** — `explain_phase_run_decision` compared NULL legacy `executor_version` to `"1.0.0"`, or IPS `5.0.0` to per-model `shared_scorer.VERSION`, before data-validation checks.
2. **Bucket / enqueue UX** — stale `phase_agg_json`, aggregate `next_phases` suffix enqueued all stages instead of JIT non-empty queues; UI did not show planner vs aggregate intent.

## Fixes shipped

| Layer | Change |
|-------|--------|
| Policy | Version compare only when `stored_version` is truthy (`phases_policy.py`); canonical `SCORING_EXECUTOR_VERSION = "5.0.0"` (`phases.py`, `phase_executors.py`, `pipeline.py`) |
| Auto-drive | `include_stale_executor=False` for enqueue; `phases_with_work_from_repair_plan`; dirty aggregate refresh on folder-buckets |
| UI | `planner_next_phases` on bucket API + RunsBucketsPanel; planner counts on run detail (`RunQueuePayloadPanel`) |
| Manual submit | Narrow `phase_values` via JIT planner; `400 nothing_to_queue` when empty |
| Diagnostics | `scripts/diagnostics/capture_run_planner_snapshot.py` |

## Verification

```bash
python -m pytest tests/test_phases_policy.py tests/test_runs_autodrive.py \
  tests/test_run_phase_planner.py tests/test_run_submit_prereq_gating.py -q
python -c "from modules.phase_executors import _get_scorer_version; print(_get_scorer_version(None))"
# Expected: 5.0.0
```

- **50 passed** (rollout bundle, 2026-05-27).
- **`tests/test_runs_autodrive.py`:** 24 passed.
- **JIT dry-run** on run-3245 folder with new code (`include_stale_executor=False`): `['keywords', 'bird_species']` — not six stages.

## Operator notes

1. **Restart WebUI** so running process loads updated `modules/*`.
2. Rebuild `/ui/` static assets if serving from `static/app/`.
3. `POST /api/runs/plan/preview` may still show large `stale_executor` counts when preview uses `include_stale_executor=True` (manual repair); auto-drive enqueue uses `False`.
4. **Pre-fix jobs** (e.g. 3245) keep their original six-phase payloads until cancelled or completed.

Optional hygiene (not required if smoke passes): back-fill NULL `executor_version` on `done` rows — see rollout plan § B4.
