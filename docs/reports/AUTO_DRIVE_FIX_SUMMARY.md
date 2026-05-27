# Auto-drive reprocessing — fix summary

**Related:** Full investigation — [AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md](AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md) · Short summary — [AUTODRIVE_REPROCESSING_SUMMARY.md](AUTODRIVE_REPROCESSING_SUMMARY.md)

## Issue

Users reported that **Auto-drive** was queuing folders that looked already processed. Run descriptions show:

> *Auto-drive queued this folder from the Runs buckets planner.*

Example: run **3245** on `/mnt/d/Photos/Z6ii/28-400mm/2025/2025-03-16` enqueued all six pipeline stages with **250** images per stage in `repair_plan_summary`, mostly due to `executor_version_changed` and `missing_data`.

---

## Root causes (two layers)

### 1. Planner false `stale_executor` hits (primary re-queue trigger)

Full analysis: [AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md](AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md).

**Symptoms:** `issue_counts_by_reason.stale_executor` ≈ 4× image count; auto-drive re-queued indexing/metadata/scoring/culling for folders that were already `done` in `image_phase_status`.

**Causes:**

1. **Legacy NULL versions** — metadata/culling rows with `executor_version=NULL` compared to registry `"1.0.0"` → immediate `executor_version_changed` (data checks never ran).
2. **Scoring version split** — IPS stored `5.0.0` (`SCORING_EXECUTOR_VERSION`) while registry/planner used `shared_scorer.VERSION` (e.g. `topiq-nr-1`) after model load → permanent mismatch.
3. **Startup-only fallback** — early `1.0.0` fallback before constant existed (partial fix, insufficient alone).

**Fixes:**

- `modules/phases_policy.py` — version compare only when `stored_version` is truthy; NULL falls through to `is_image_*_complete()`.
- `SCORING_EXECUTOR_VERSION = "5.0.0"` in `modules/phases.py`; `_get_scorer_version()` always returns it (not per-model `VERSION`).
- `modules/pipeline.py` — IPS writes use `SCORING_EXECUTOR_VERSION` for scoring phase rows.

**Verify:**

```bash
python -c "from modules.phase_executors import _get_scorer_version; print(_get_scorer_version(None))"
# Expected: 5.0.0
```

**Files:** `modules/phases.py`, `modules/phases_policy.py`, `modules/phase_executors.py`, `modules/pipeline.py`, `tests/test_phases_policy.py`

---

### 2. Bucket planner / enqueue UX (misleading “full re-run”)

**Symptom:** Runs buckets UI showed all phases `not_started 0/250` while a job was actively indexing; auto-drive enqueued a **six-phase suffix** even when only some stages had JIT work.

**Causes:**

| Problem | Mechanism |
|--------|-----------|
| Stale folder aggregates | `build_folder_buckets` used `get_all_folder_phase_summaries_bulk(include_dirty_cache=False)` — **dirty folders omitted** → synthetic `not_started` rows. |
| Phase suffix enqueue | `next_phases` = all stages from first incomplete folder-summary phase, not per-image JIT queues. |
| UI | No visibility into `repair_plan_summary.stage_queues` at enqueue time. |

**Fixes** (`modules/runs_autodrive.py`, `modules/api.py`, frontend):

1. **`_resolve_folder_phase_summary`** — force-refresh when bulk cache is missing or `phase_agg_dirty=1` (up to `refresh_dirty_limit`, default **100** on `GET /api/runs/folder-buckets`).
2. **`phases_with_work_from_repair_plan`** — auto-drive enqueue uses dry-run `build_validation_repair_plan` and only schedules stages with **non-empty** `stage_queues` (skips legacy `clustering` alias).
3. **`RunQueuePayloadPanel`** — shows planner queue lengths and `issue_counts_by_reason` from enqueue payload; notes JIT may skip empty phases at dispatch.

**Diagnostics script:**

```bash
python scripts/diagnostics/capture_run_planner_snapshot.py 3245
```

**Tests:** `tests/test_runs_autodrive.py` (dirty refresh, repair-plan phases, enqueue narrowing).

**Files:** `modules/runs_autodrive.py`, `modules/api.py`, `frontend/src/components/runs/RunQueuePayloadPanel.tsx`, `scripts/diagnostics/capture_run_planner_snapshot.py`, `tests/test_runs_autodrive.py`

---

## How planning actually works

```text
Auto-drive bucket planner     →  folder phase_agg_json (aggregate IPS)
                              →  picks folder + next_phases suffix

Enqueue (auto-drive / submit) →  build_validation_repair_plan (per-image JIT)

Per-phase dispatch            →  plan_phase + work claims; skip empty phases
```

Canonical mode: `process_stale_or_missing` — see [RUN_OPTIONS_MODE_MATRIX.md](../technical/RUN_OPTIONS_MODE_MATRIX.md).

**Important:** Fixing (1) reduces false `stale_executor` scoring rework. Fixes (2) improve accuracy of **which folders/stages** get queued and what the UI shows. Already-queued runs (e.g. 3245) keep their original `target_phases` until cancelled or completed.

---

## After deploy

1. Restart WebUI so phase registry picks up `SCORING_EXECUTOR_VERSION`.
2. Rebuild React UI if using bundled `/ui/` assets.
3. For a suspect folder, `POST /api/runs/plan/preview` with `scope_paths` — confirm `stage_queues` lengths before auto-drive.
4. New auto-drive jobs should enqueue **only stages with non-empty** planner queues.
