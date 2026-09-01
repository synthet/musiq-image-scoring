---
type: Report
title: Phantom culling `done` — folders that were never clustered
description: The gallery showed no stacks for recent shoots. The auto-drive preflight had been marking never-clustered images culling-complete, hiding 74 folders from Drive to Complete permanently. Root cause traced through the audit log, fixed, and the backlog re-clustered.
resource: docs/reports/PHANTOM_CULLING_DONE_2026-09-01.md
tags: [culling, clustering, auto-drive, phase-status, stacks, incident, postmortem]
timestamp: 2026-09-01T00:00:00Z
okf_version: 0.1
---

# Phantom culling `done` — folders that were never clustered

**Reporter:** dmnsy (Claude Opus 5 assist)
**Trigger:** Gallery showed 883 images from 2026-08-25 as 883 separate tiles with the Stacks toggle on, including obvious ten-frame bursts.
**Status:** Fixed — [PR #343](https://github.com/synthet/image-scoring-backend/pull/343), closing [#340](https://github.com/synthet/image-scoring-backend/issues/340) and [#341](https://github.com/synthet/image-scoring-backend/issues/341). Backlog re-clustered; [#342](https://github.com/synthet/image-scoring-backend/issues/342) filed and deliberately not started.
**See also:** [CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md](CULLING_NO_STACKS_INVESTIGATION_2026-03-15.md) — the *same symptom* from a different cause (SelectionRunner phase-order bug, fixed 2026-03). Check both when "culling done but no stacks" recurs. Also [AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md](AUTODRIVE_REPROCESSING_INVESTIGATION_2026-05-26.md) — a different auto-drive defect in the same policy layer.

## TL;DR

Images were **marked culled without ever being clustered**. They carried a `cull_decision` and a rating, but `stack_id`, `sub_stack_id` and `burst_uuid` were all NULL, and their `culling` phase row read `done`. Terminal status means the folder rollup counts culling complete, so **Drive to Complete skipped those folders permanently** and the workflow-heal predicate never got a chance to look. Nothing in the system considered the work outstanding.

**74 folders / 2,662 images** had zero stacks. **1,916 of them had no default-space (`mobilenet_v2_imagenet_gap`) embedding at all — and every single one of those had `stack_id IS NULL`.** That correlation is exact and it is the proof: `ClusteringEngine` computes and persists that embedding itself (`modules/clustering.py:210`, `:921-928`), so its absence means the clustering pass never touched the image.

## Root cause

`runs_autodrive._reconcile_stale_ips_for_drive` ran on every drive preflight:

```python
db.reconcile_phantom_complete_image_phases(
    ("indexing", "metadata", "scoring", "keywords", "culling"), limit=5000,
)
```

It marks `done` any image where `NOT (get_phase_incomplete_sql(code))`, via `set_image_phase_status(iid, code, "done")` with no `executor_version` and no `job_id` (`modules/db_legacy.py:10212`).

For culling that predicate delegates to `get_culling_incomplete_predicate_sql` (`db_legacy.py:9925`), which tests **data shape** — `cull_decision` present, a default embedding present, folder time-cohesion. None of that implies clustering ran and assigned stacks. Culling's work product is a **folder-level grouping decision**; unlike a score or a keyword it cannot be inferred from a single image's row.

### Evidence from `auditlog`

| field | value |
|---|---|
| table / phase | `image_phase_status` / `culling` |
| patch | `{"op":"replace","path":"/status","value":"done","oldValue":"not_started"}` × **672** |
| thread | `runs-autodrive-batch` |
| `run_id` | NULL |
| window | 2026-08-30 16:55:39 → 16:56:02 (**23 seconds**) |

534 images cannot cluster in 23 seconds, and every genuine writer stamps its version — `clustering.py:1047` passes `executor_version=CLUSTER_VERSION, job_id=job_id`, and `selection_runner.py:287` does the same on the failure path. This was a bulk status flip, not a clustering run.

### Why the existing safety net didn't fire

`_apply_done_postcondition_gate` (`db_legacy.py:13746-13800`) exists for precisely this case and would have downgraded the write to `failed`. It is gated behind `phases.enforce_done_postconditions`, default `False`, and `config.json` has `"phases": {}`. The predicate it uses, `is_image_culling_similarity_artefacts_missing` (`db_legacy.py:10683`), describes this exact failure mode in its own docstring and was reachable from nowhere else.

## Two adjacent defects found on the way

### 1. Stale-running reaper never invalidated the folder rollup

`reconcile_stale_running_image_phases` (`db_legacy.py:6345`) flips rows `running → failed` with a raw UPDATE and never called `invalidate_folder_phase_aggregates`. Its sibling `reconcile_stale_running_phases_for_jobs` collects `folder_ids` before the update (`:7912`) and invalidates after (`:8001`).

A container restart on 2026-08-31 interrupted selection job 6696 on `/mnt/d/Photos/Z8/180-600mm/2026/2026-08-23`. The no-heartbeat reaper flipped its 4,898 `running` culling rows to `failed` at 13:34-13:45, but `folders.phase_agg_json` kept a `culling: running 4898` snapshot from 05:09 with `phase_agg_dirty = 0`. `_build_bucket_from_summary` (`runs_autodrive.py:1388`) read `running > 0`, bucketed the folder `in_flight`, and the drive reported `waiting_in_flight` with `schedulable 0` — **for eight hours, waiting on a job that had already finished**.

It was a deadlock: the reconcile that would repair it runs in `_apply_preflight`, which only executes once a run is planned, and no run is planned while the drive is waiting.

### 2. `finished_at` not cleared on re-run

`set_image_phase_status`, on the `running` branch of the UPDATE path, set `started_at = now` but left the previous run's `finished_at`. `_duration_ms_from_phase_timestamps` (`:7730`) then returned `finished − started < 0` and every in-flight work item on the run detail page rendered a negative duration:

```
status=running  started_at=2026-09-01T02:32:54  finished_at=2026-08-30T16:55:41  → -121032.99s
```

The stale `finished_at` there is the phantom-reconcile write itself — a neat confirmation of the whole chain.

## The fix

**#340 — `fix(culling)`**

- `culling` dropped from the drive preflight's phantom-reconcile tuple.
- `reconcile_phantom_complete_image_phases` now refuses a culling `done` when `is_image_culling_similarity_artefacts_missing`, so no caller — including the explicit maintenance script — can make the unsafe write. Applied before the dry-run count so preview and apply agree.
- New `reset_false_complete_culling_phases`, mirroring `reset_false_complete_metadata_phases` and backed by a new set-based `_sql_culling_similarity_artefacts_missing`, wired into the same preflight. Poisoned rows return to `not_started`; `set_image_phase_status` marks the folder aggregate dirty in-transaction, so the drive re-buckets to `awaiting_culling` unattended. **No one-shot repair script.**

**#341 — `fix(db)`** — collect folder ids before the reap loop and invalidate after; clear `finished_at` alongside the `started_at` stamp.

`phases.enforce_done_postconditions` left off — the code guard makes the gate redundant for this path. No schema change, no migration, no frontend change.

## Verification

| check | result |
|---|---|
| Fast subset (`not gpu and not db and not ml`) | **2053 passed**, 9 failed |
| Same command on pristine `master` worktree | 2039 passed, **the same 9 failed** |
| Net | **+14 new tests, zero regressions** |
| `tests/test_runs_autodrive.py` | 72 passed |
| `ruff` on touched files | 190 baseline → **190**, identical breakdown |

The 9 failures are pre-existing and environmental (git-ignored `config.json` absent from the worktree, no DB, absent sample dirs). They were verified against a clean `master` checkout rather than assumed.

New tests: `tests/test_culling_false_complete_reset.py`, `tests/test_phase_status_timestamps.py`, plus four cases added to `tests/test_phantom_phase_reconcile.py`.

## Recovery

Re-clustering used the existing `scripts/maintenance/queue_clustering_no_stacks_folders.py --require-culling-done --enqueue`, which force-rescans by default so a phantom `done` cannot short-circuit it. Jobs **6720-6733** (14 largest folders, 2,522 images), then **6734-6793** (60 small folders, 140 images).

| folder | images | stacked | stacks |
|---|---|---|---|
| `Z8/180-600mm/2026/2026-08-25` | 534 | 499 | 60 |
| `Z8/105mm/2026/2026-06-07` | 415 | 407 | 8 |
| `Z8/180-600mm/2026/2026-05-31` | 388 | 376 | 47 |
| `Z6ii/28-400mm/2026/2026-08-25` | 327 | 305 | 60 |
| `Z8/40mm/2026/2026-08-27` | 256 | 189 | 57 |
| `Z6ii/28mm/2026/2026-08-25` | 22 | 20 | 5 |

**Never-clustered count: 1,916 → 5.**

### Regression guard

```sql
WITH sp AS (SELECT id FROM embedding_spaces WHERE code='mobilenet_v2_imagenet_gap' AND COALESCE(active,1)=1 LIMIT 1)
SELECT COUNT(*) FROM images i
WHERE i.stack_id IS NULL
  AND NOT EXISTS (SELECT 1 FROM image_embeddings ie
                  WHERE ie.image_id=i.id AND ie.embedding_space_id=(SELECT id FROM sp));
-- baseline 2026-09-01: 1916
```

## Open items

- **[#342](https://github.com/synthet/image-scoring-backend/issues/342)** — `/ui/runs/6720` reported `145,636 / 534 work items`. Traced to the WebSocket `job_progress` event (`clustering.py:1183-1189` → `adaptBackendMessage.ts:111` → `wsStore` → `StagePanel.tsx:85`), but every `cur` emitted by `_cluster_images_impl` is arithmetically bounded by `len(images_rows)`, so static reading does not explain the number. **Deliberately not fixed** — the next step is capturing the live payload, not guessing. `WorkflowGraph.tsx:56` also divides without clamping, unlike `StagePanel.tsx:87`.
- The `--require-culling-done` audit will not return literal zero: 35 of the remaining folders hold a single image, which can never form a stack yet still matches "folder with no stack assignments". A `HAVING COUNT(*) >= 2` floor would make that check a clean zero-or-alarm signal.
- `phases.enforce_done_postconditions` remains off. Turning it on would convert any future phantom `done` into a visible `failed` library-wide — broader than this fix, and `config.json` is git-ignored so it would be a local-only change.
