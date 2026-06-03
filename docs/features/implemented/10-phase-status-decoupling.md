# Phase Status Decoupling

**Shipped:** May 2026  
**Primary modules:** `modules/db_legacy.py`, `modules/phases.py`, `frontend/src/pages/ImageInspectorPage.tsx`, `scripts/maintenance/reconcile_phase_status.py`

This document details the transition from an overloaded, history-based phase status model to a decoupled architecture where the database strictly reflects data completeness, and the UI presents a distinct "Last Run Activity" telemetry view.

## The Problem

Historically, the `image_phase_status` (IPS) table served dual purposes:
1. **Data State Cache:** Tracking whether an image actually had the necessary data (e.g., scores, metadata) for a given phase.
2. **Execution History:** Tracking what the most recent runner did (e.g., marking a phase `skipped` if the runner found the image already processed).

This overloading caused UX issues. When a fast-path runner skipped an already-processed image to save time, it clobbered the existing `done` status in the DB with `skipped`. To the user, it appeared as though completed work had regressed or been lost, even though the underlying data (e.g., `score_general`) remained intact.

## The Solution: A+C Hybrid Approach

The architecture was decoupled to separate the *data reality* from the *telemetry*:

### 1. Backend: Strict Data-Driven Cache (Option C)
The backend now treats `image_phase_status` as a strict ground-truth cache of actual data completeness. The `ALLOWED_TRANSITIONS` state machine in `modules/phases.py` does not include `done → skipped`, preventing runners from clobbering completed status with fast-path skip entries. By default (`database.strict_phase_transitions = false`), illegal transitions are logged as warnings and proceed; setting the flag to `true` promotes them to hard errors. Runners record per-run skips via `job_image_actions` instead of mutating IPS.

### 2. Frontend: Two-Tiered UI (Option A)
The Image Inspector (`/ui/images/:id`) now displays a bifurcated view:
- **Data Status:** The true state of the phase (`not_started`, `running`, `done`, `failed`), directly sourced from `image_phase_status`.
- **Last Run Activity:** Telemetry indicating what the pipeline did during the last attempt (e.g., `processed`, `skipped`, `failed`, `unchanged`), accompanied by the runner's recorded reason.

## Implementation Details

### API Enrichment
The `get_image_phase_statuses` and `get_batch_image_phase_statuses` functions in `modules/db_legacy.py` were modified. They now perform a subquery against `job_image_actions` using a window function (`ROW_NUMBER() OVER(PARTITION BY image_id, phase_code ORDER BY created_at DESC)`) to fetch the most recent execution telemetry for each phase. The single-image variant (`get_image_phase_statuses`) partitions by `phase_code` only, since `image_id` is already fixed by the `WHERE` clause. This data is appended to the API payload under the `last_run_action` key, containing `action`, `reason`, `created_at`, and `job_id`.

### Frontend Updates
The `ImagePhaseStatusRow` TypeScript interface in `frontend/src/types/api.ts` was expanded to include `last_run_action`. The `PhaseStatusTable` component in `ImageInspectorPage.tsx` was redesigned to render this new telemetry via color-coded badges (green for `processed`, amber for `skipped`, red for `failed`, muted for `unchanged`), ensuring users can see both the persistent `done` data state and the transient `skipped` run activity simultaneously.

### Reconciliation Maintenance
A script was introduced at `scripts/maintenance/reconcile_phase_status.py` to identify and heal "status drift" across the database. It compares the `image_phase_status` table against the `images` table and enforces the following invariants:
- **Scoring:** `score_general IS NOT NULL AND score_general > 0`
- **Metadata:** `rating IS NOT NULL AND label IS NOT NULL`
- **Indexing:** `id IS NOT NULL` (image exists in the database; the inline heal variant `_heal_stale_phase_flags` in `db_legacy.py` uses the stricter `image_embedding IS NOT NULL`)
- **Keywords:** `keywords IS NOT NULL AND keywords != ''`

If data exists but the status is not `done`, the script heals the row to `done`. If the status is `done` but data is missing, it downgrades the row to `not_started`. This ensures the strict cache contract remains unbroken.

An additional inline healing function, `_heal_stale_phase_flags`, runs automatically on folder force-refresh and applies the same logic per-folder with tighter invariants (e.g., checking `image_embedding IS NOT NULL` for indexing and `image_keywords` table rows for keywords).
