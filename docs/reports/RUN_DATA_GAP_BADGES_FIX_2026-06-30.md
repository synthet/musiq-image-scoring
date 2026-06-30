---
type: Report
title: Misleading "Data gaps" badges on completed runs — fix
description: Why completed single-phase auto-drive runs showed a permanent "Data gaps" badge, and the two-part fix (hash-based indexing completeness + phase-scoped post-run audit badge).
resource: modules/db_legacy.py
tags: [reports, auto-drive, post-run-audit, runs, indexing, badges]
timestamp: 2026-06-30T00:00:00Z
okf_version: 0.1
---

# Misleading "Data gaps" badges on completed runs

Point-in-time report for the `RunCard` "Data gaps" warning firing on auto-drive runs that completed exactly the work they were asked to do (verified against live DB for run **4555**).

**Status:** Fixed (2026-06-30). New runs are correct without backfill; clearing the ~4,473 already-frozen historical badges is an optional follow-up (see [Historical badges](#historical-badges)).

**Related:** [AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md](AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md) · [AUTO_DRIVE_FIX_SUMMARY.md](AUTO_DRIVE_FIX_SUMMARY.md) · post-run audit config in [technical/CONFIG.md](../technical/CONFIG.md)

## TL;DR

The "Data gaps" badge ([`frontend/src/components/runs/RunCard.tsx`](../../frontend/src/components/runs/RunCard.tsx)) fires when `post_run_audit.status == 'issues_remaining'`. That status is computed once at job completion by `run_post_completion_data_quality_audit` (`modules/db_legacy.py`) and frozen into `queue_payload`. Two defects combined to make a clean single-phase run look like it left data gaps — permanently.

## Root cause

### Defect 1 — definitional bug

`is_image_indexing_complete()` returned true only if the image had a default-space embedding (`mobilenet_v2_imagenet_gap`). That embedding is produced by the **Culling** phase (`modules/clustering.py`), **not** indexing. The phase predicate `get_phase_incomplete_sql('indexing')` already (correctly) tested `image_hash`, so the two definitions disagreed: a freshly-indexed image with a hash but no embedding was judged "indexing-incomplete."

### Defect 2 — full-pipeline audit on a single-phase run

Auto-drive runs **one phase per job** (run 4555: `job_type='indexing'`, only indexing executed), but `target_phases` lists the whole pipeline `[indexing, metadata, scoring, culling]`. The audit checked all four phases, so downstream culling was correctly "not started" → `issues_remaining` → badge, frozen forever.

Both fixes are required together: the definitional fix alone still leaves the culling gap; the scope fix alone still trips on `indexing_missing_data`.

### Data scope

For run 4555's 9 images: all had `image_hash`, none had any embedding. Library-wide only ~**424 / 64,884** images lack the default embedding, so this was overwhelmingly **badge noise**, not lost data.

## The fix

### 1. Hash-based indexing completeness

`is_image_indexing_complete` (`modules/db_legacy.py`) now tests `image_hash` presence (postgres + legacy branches), mirroring `get_phase_incomplete_sql('indexing')`. The stale NOTE documenting the old embedding-vs-hash mismatch was updated. This aligns the JIT planner/policy (`modules/phases_policy.py`) so indexing is "done == hash present."

### 2. Phase-scoped audit badge

`run_post_completion_data_quality_audit` (`modules/db_legacy.py`):

- `SELECT` now fetches `job_type`; a new `_audit_job_type_to_phase()` maps it to a single phase (reusing the `score→scoring`, `tag/tagging→keywords`, `cluster/clustering/selection→culling` alias set).
- Badge `status`/`severity` derive from **only the executed phase's** queue and issue-counts.
- The full plan still populates `stage_queues`, and two new fields are stored: `executed_phases` and `pipeline_status` (whole-pipeline `issues_remaining`/`clean`) for chaining and diagnostics.
- A multi-phase / unknown `job_type` (e.g. `pipeline`) falls back to whole-pipeline badge status.

### 3. Preserve auto-drive chaining

`maybe_schedule_post_audit_followup` (`modules/runs_autodrive.py`) now gates on `pipeline_status` (falling back to `status` for audits written before the field existed) instead of the now phase-scoped `status`. A clean badge on a single-phase run therefore still enqueues downstream phase work — phase progression is preserved while the badge stops lying.

### 4. Tests

- `tests/test_embedding_presence.py` — `is_image_indexing_complete` is hash-based (firebird present/absent/blank; postgres uses-hash).
- `tests/test_post_run_audit.py` — indexing run with downstream culling work → `status: clean`, `pipeline_status: issues_remaining`, full `stage_queues` retained; executed-phase gap → badge fires; multi-phase → full status.
- `tests/test_runs_autodrive.py` — follow-up fires when badge clean but pipeline dirty; skips when both clean.

## Historical badges

~4,473 already-completed runs have a frozen `post_run_audit` and will keep showing badges until re-audited. An optional, `--limit`-bounded maintenance script can re-run the audit for completed jobs currently flagged `issues_remaining`, recomputing under the new logic. Flagged optional due to cost; new runs are correct without it.

## Validation

- Unit subset (mock-based) green: indexing-complete + audit-scoping + chaining tests pass.
- Pending before merge: postgres-marked path (`pytest -m postgres`) and a live indexing-only auto-drive run confirming `/api/runs/<id>/diagnostics` reports `status: clean` with `pipeline_status: issues_remaining`, and that the next phase still gets enqueued.
