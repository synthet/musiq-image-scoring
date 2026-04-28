# Fix: Run Thumbnail Generation Failure

**Date:** 2026-04-11
**Severity:** High (data loss — thumbnails silently not generated for entire runs)
**Status:** Implemented, pending release

---

## Problem Statement

Run #989 processed 3,364 images in `D:\Photos\Z8\180-600mm\2026\2026-04-08` but completed with **all images missing thumbnails** (`thumbnail_path = NULL`). The metadata phase (responsible for EXIF extraction, thumbnail generation, UUID assignment) reported "completed" with **0 work items** — it started but found no images to process.

### Symptoms

- Thumbnails missing for all images in a run (Electron gallery shows broken placeholders)
- `image_phase_status` has no metadata entries despite the phase being marked "completed" in `job_phases`
- Affects both newly indexed images and previously indexed images that never had metadata processed

### Affected Paths

Both pipeline entry points are vulnerable:

| Entry Point | Used By | Phase Planning |
|-------------|---------|----------------|
| `PipelineOrchestrator.start()` | Gradio UI, CLI | Computes phase plan from `get_folder_phase_summary()` snapshot |
| `/runs/submit` API + `JobDispatcher` | React SPA (`/ui/`) | Creates all requested `job_phases` upfront |

---

## Root Causes

### RC-1: Metadata runner non-recursive query + stale cache (PRIMARY)

**File:** `modules/metadata_runner.py:122`

The metadata runner calls `db.get_images_by_folder(input_path)` which:
1. Uses `WHERE i.folder_id = ?` — exact single-folder match, no subfolder traversal
2. Caches results in `_folder_images_cache` (30s TTL) keyed by `os.path.normpath(path)`

**Cache key mismatch on Windows host:** The indexing runner invalidates cache entries using WSL-normalized paths (e.g., `\mnt\d\Photos\...` after `os.path.normpath` on win32), but the metadata runner queries with Windows-normalized paths (e.g., `D:\Photos\...`). These produce different cache keys — indexing's invalidation misses the metadata runner's lookup, potentially serving stale (empty) results.

**Non-recursive scope:** If the run targets a parent folder (e.g., `2026`) but images are registered under a child folder (`2026-04-08`), `get_images_by_folder` returns 0 rows. This contradicts `get_folder_phase_summary`, which counts images recursively across the entire subtree.

### RC-2: `get_folder_fulfillment_stats` was non-recursive

**File:** `modules/db.py` (old `get_folder_fulfillment_stats`)

The orchestrator's fulfillment safety check (`pipeline_orchestrator.py:92-103`) used `get_folder_fulfillment_stats(folder_id)` which queried `WHERE folder_id = ?` — single folder only. This was inconsistent with `get_folder_phase_summary` which uses subtree scope. For parent-folder runs, `total=0` made the check accidentally pass; for leaf-folder runs with subfolder images, it could miss gaps.

### RC-3: Orchestrator static phase plan

**File:** `modules/pipeline_orchestrator.py:71`

The orchestrator computes its phase plan once at `start()` time from `get_folder_phase_summary()`. This snapshot reflects only images currently in the DB. When indexing adds new images, downstream phases (metadata, scoring, etc.) that were excluded from the plan as "done" never get a chance to process the new images.

### RC-4: Tagging runner same non-recursive pattern

**File:** `modules/tagging.py:490`

Identical to RC-1 — `get_images_by_folder(input_path)` with no cache invalidation or recursive fallback.

---

## Fixes Applied

### Fix 1: Metadata runner — cache invalidation + recursive fallback

**File:** `modules/metadata_runner.py:121-143`

```python
elif os.path.isdir(input_path):
    db.invalidate_folder_images_cache()          # flush cross-format stale keys
    all_images = db.get_images_by_folder(input_path)
    if not all_images:                            # recursive fallback
        for folder_path in db.list_folder_paths_under_scope(scope_path):
            for row in db.get_images_by_folder(folder_path):
                # deduplicate by image id
```

- Clears the entire in-memory `_folder_images_cache` dict before querying (cheap, avoids WSL/Windows key mismatch)
- If direct lookup returns empty, falls back to `list_folder_paths_under_scope()` iteration — same subtree scope as `get_folder_phase_summary`
- Pattern borrowed from `selection_runner.py` which already handles this correctly

### Fix 2: Subtree-scoped fulfillment stats

**File:** `modules/db.py` — new `get_folder_fulfillment_stats_for_path(folder_path)`

Replaces the old `get_folder_fulfillment_stats(folder_id)` with a path-based function that:
- Uses `WHERE folder_id IN (SELECT id FROM folders WHERE path = ? OR path LIKE ?)` — same subtree scope as `get_folder_phase_summary`
- Checks both `thumbnail_path` and `thumbnail_path_win` for thumbnail fulfillment
- Tracks indexing IPS completion (`done` + `skipped` = satisfied) via `indexing_done` / `indexing_pct`
- Old function now delegates to the new one

### Fix 3: Orchestrator — force downstream phases when indexing is in plan

**File:** `modules/pipeline_orchestrator.py:75-136`

```python
indexing_in_plan = False
for phase in self.PHASE_ORDER:
    ...
    if phase_status == "done":
        if indexing_in_plan:
            # Include it — indexing may add new images
            pass
        else:
            # Existing fulfillment check (now subtree-scoped)
            ...
    phase_plan.append(code)
    if code == PhaseCode.INDEXING.value:
        indexing_in_plan = True
```

When indexing is included in the plan, all downstream phases are included regardless of their "done" status. The per-image skip logic in each runner (`skip_existing` / `metadata_already_done`) efficiently handles already-processed images with minimal overhead.

### Fix 4: Tagging runner — same pattern as Fix 1

**File:** `modules/tagging.py:487-507`

Cache invalidation + recursive fallback, identical to the metadata runner fix.

### Bonus: Multi-phase job_phases "running" race fix

**File:** `modules/db.py` — `_resolve_multi_phase_job_phases_sync_code`

Fixed priority order: now checks for an already-`running` phase first before promoting `queued`/`pending` phases. Previously, repeated `update_job_status(..., "running")` calls (e.g., runner heartbeats) could promote the next pending stage while the current one was still active, causing multiple stages to show "Running" in the UI.

New `reconcile_duplicate_running_job_phases()` function repairs historical data with this issue.

---

## Files Modified

| File | Lines | Change |
|------|-------|--------|
| `modules/metadata_runner.py` | +25 | Cache invalidation + recursive fallback |
| `modules/tagging.py` | +18 | Same recursive fix |
| `modules/pipeline_orchestrator.py` | +40 | `indexing_in_plan` guard + subtree fulfillment |
| `modules/db.py` | +215 | `get_folder_fulfillment_stats_for_path`, `reconcile_duplicate_running_job_phases`, `_resolve_multi_phase_job_phases_sync_code` fix |
| `tests/test_pipeline_orchestrator_fakes.py` | +80 | Test: orchestrator reopens phases when fulfillment stats show gaps |

---

## Testing

- **89/89** pipeline workflow matrix integration tests pass (`test_pipeline_workflow_matrix.py`)
- New test `test_orchestrator_reopens_indexing_when_summary_done_but_indexing_pct_low` validates Fix 3
- No regressions in fast test suite (`pytest -m "not gpu and not db and not ml and not firebird"`)

## Verification Checklist

- [ ] Submit a run for a folder with existing fully-processed images + new unprocessed files on disk
- [ ] Verify metadata phase processes newly indexed images (check `image_phase_status` entries)
- [ ] Verify thumbnails are generated (check `thumbnail_path` column and `thumbnails/` directory)
- [ ] Verify `/ui/runs/<id>` shows work items for the metadata phase
- [ ] Verify re-running a fully-processed folder with no new images completes quickly (skips efficiently)
