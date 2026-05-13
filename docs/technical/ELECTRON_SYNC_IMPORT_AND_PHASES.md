# Electron sync import and pipeline phase semantics

How **Driftara Gallery** “**Sync from device**” interacts with PostgreSQL **`image_phase_status`**, **`jobs`**, and the Python pipeline — and how that relates to product stage names (`phase_code` vs UI).

**Operational workflow (IPC, progress counters, logs):** [image-scoring-gallery `docs/features/implemented/06-sync-from-device-workflow.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/06-sync-from-device-workflow.md).

## Canonical terminology

Use **[PIPELINE_TERMINOLOGY.md](PIPELINE_TERMINOLOGY.md)**. In short:

| DB `phase_code` | Product name | Meaning |
|-----------------|---------------|---------|
| `indexing` | **Discovery** | Register the file in `images` / folder; **not** “all preprocessing finished.” |
| `metadata` | **Inspection** | EXIF/XMP and thumbnails in the pipeline sense. |
| `scoring` | **Quality Analysis** | ML scores. |
| `culling` | **Similarity Clustering** | Stacks / similarity. |
| `keywords` | **Tagging** | Keywords/captions. |

The React **Image Inspector** (`/ui/images/:id`) lists **internal codes** (e.g. `indexing`) in the **Pipeline phases** table — map them with the table above.

## What Electron guarantees after sync

After a successful **import** step of sync, the gallery:

1. Inserts **`images`** rows (destination paths).
2. Calls **`markImageIndexingPhaseDone`** (gallery `electron/db.ts`) so **`image_phase_status`** for phase **`indexing`** is **`done`** for those ids.
3. Invokes **`scheduleProcessingForImages`**, which:
   - Submits **`metadata`**, **`score`**, **`tag`**, **`cluster`** (maps to `phase_code`: `metadata`, `scoring`, `keywords`, `culling`) — **not** `indexing`, because Discovery is already marked complete locally.
   - **As of gallery v7.7 (G5):** also calls **`markImagePhasesPending(imageIds)`** in the **API-success** branch, not only on failure. This pre-seeds **`image_phase_status`** rows with **`status = 'not_started'`** for `metadata`, `scoring`, `keywords`, `culling` so the full pipeline is visible immediately, and so runners see a non-empty scope when they iterate IPS rows. Insert uses `ON CONFLICT DO NOTHING` — safe to call repeatedly; never downgrades a row the backend has already advanced.

So seeing **`indexing` → Done** for a just-imported image is **expected**. After G5, all four downstream phases will have **`not_started`** rows from the moment the API submit succeeds, instead of appearing only when each runner first touches the image.

## Jobs and queues

- A successful API submit creates/updates processing in the **`jobs`** table; the UI may show **“Submitted to backend (job N)”** where **N** aligns with **`jobs.id`** / workflow run id usage in the React app.
- Header badges such as **“N active · M queued”** on the Web UI reflect dispatcher/queue state; they indicate remaining work, **not** a failure of the `indexing` phase.

## `phase_statuses` on the image inspector

**As of backend G7:** `db.get_image_phase_statuses(image_id)` LEFT JOINs from **`pipeline_phases`** with `COALESCE(enabled, 1) = 1`, so every enabled phase code appears in the result. Phases without an **`image_phase_status`** row default to:

```json
{ "status": "not_started", "updated_at": null, "attempt_count": 0, ... }
```

This applies to both `get_image_phase_statuses` (single image) and `get_batch_image_phase_statuses` (batch). The React **Image Inspector** (`/ui/images/:id`) will now always list all five pipeline phases (plus `bird_species` when enabled in the catalog), even for images that the backend has not started processing yet.

**Before G7 / pre-fix behavior:** the inspector showed only rows that existed in **`image_phase_status`**. Combined with the gallery only writing an `indexing=done` row at import time, a freshly synced image would show **just one row** in the inspector until each subsequent runner created or updated rows. The "missing" downstream rows were misread as "this phase will never run" rather than "queued/not-yet-touched."

## Gallery “Phases” sidebar vs database

**Before G6** the Electron gallery **ImageViewer** “Phases” block used **client heuristics** (cached EXIF load, `score_general` non-null, presence of `keywords`, rating/label) — it did **not** mirror `image_phase_status` 1:1, and could go green on Inspection / Tagging while the corresponding DB phases were still `not_started`.

**As of gallery v7.7 (G6):** the sidebar fetches `image_phase_status` directly via a new `getImagePhaseStatuses(imageId)` IPC path (Electron `db.ts` → preload → `bridge`, plus the browser-mode `GET /db/image/:id/phase-statuses` endpoint). It renders each phase from the real status field (`Pending` for `not_started`, `Running`, `Completed` for `done`, `Skipped`, `Failed`). The legacy heuristic is kept only as a fallback rendered for the brief moment before the IPS fetch resolves, or when the query errors.

This means **Pending** in the gallery now matches **`not_started`** in `image_phase_status` — a Quality Analysis row that stays `Pending` after a run completes is a real signal that the scoring runner produced no rows for that image (see “Known issues” below).

## Verification ideas (Postgres)

Illustrative checks (adjust schema names if needed):

```sql
-- Replace :id with images.id
SELECT pp.code, ips.status, ips.updated_at, ips.finished_at
FROM image_phase_status ips
JOIN pipeline_phases pp ON pp.id = ips.phase_id
WHERE ips.image_id = :id
ORDER BY pp.code;
```

For the run shown after sync:

```sql
SELECT id, job_type, status, created_at, updated_at
FROM jobs
WHERE id = :job_id;
```

## Known issues (observed on run 2365, 2026-05-10)

End-to-end monitoring of one full sync→pipeline run surfaced three issues that are **separate from** the gallery↔backend contract above. They affect what the user sees in `/ui/runs/:id` and `/ui/images/:id`, even with G1/G5/G6/G7 deployed.

1. **Scoring stage of a multi-stage WorkflowRun silently produces zero results when `skip_existing=true`** — [#156](https://github.com/synthet/image-scoring-backend/issues/156). Run **2365** (a gallery-submitted workflow: `stage_codes=["metadata","score","tag","cluster"]`, `skip_existing=true`, 733 `resolved_image_ids`) marked `job_phases.scoring` as `completed` in **3 seconds** with `images_in_scope=0`, no `image_phase_status` rows, no captured log — yet all 733 images stayed with `score_general IS NULL`. Re-submitting the **same 733 ids as a single-stage scoring job** with `skip_existing=false` (run **2374**) worked: 38 min runtime, 733 scored. The bug is not in `scoring.py:256` (initial RCA was wrong — the webui runs in WSL where `/mnt/d/...` paths resolve correctly). The actual cause is somewhere in the multi-stage workflow dispatch / `skip_existing=true` interaction; `jobs.log` is `NULL` for 2365 so root cause isn't yet pinned. Workaround: re-submit scoring alone with `skip_existing=false`.

2. **`SelectionRunner.start_batch` ignores `resolved_image_ids`** — [#157](https://github.com/synthet/image-scoring-backend/issues/157). [`modules/job_dispatcher.py:395-400`](https://github.com/synthet/image-scoring-backend/blob/master/modules/job_dispatcher.py#L395-L400) explicitly logs *"Selection runner does not accept resolved_image_ids yet; culling queue constraints are advisory only"*. So passing an id list to a `selection` job has no effect — scoping is by `input_path` only. Separately, an `interrupted` selection job (e.g. job 2379) leaves IPS `culling` rows stuck in `running` state with no automatic recovery; `reconcile_stale_running_phases_for_jobs` exists but is not auto-invoked. The "completed in seconds, zero scope" symptom originally attributed to a runner short-circuit is actually downstream of #156 (no scores → nothing to cluster).

3. **`job_phases` counters are not flushed during a phase, only at finalize** — [#158](https://github.com/synthet/image-scoring-backend/issues/158). `images_in_scope` / `images_processed` / `images_skipped` stay at 0 for the entire active phase and only update when the phase completes via `ReportCollector.finalize()` (`modules/report_collector.py`). The Runs UI faithfully shows `0 / 0 work items` during the active phase even when work is happening — confirmed for run 2365 metadata phase, which had 86 → 600 → 733 `image_phase_status` rows transitioning while `job_phases.metadata.images_processed` stayed 0 until the very end.

## Related

- **[AGENT_COORDINATION.md](AGENT_COORDINATION.md)** — cross-repo contracts.
- **[RUNS_WALKTHROUGH.md](RUNS_WALKTHROUGH.md)** — runs and queue behavior.
- **Gallery** — `electron/scheduleProcessing.ts`, `electron/db.ts` (`markImageIndexingPhaseDone`, `markImagePhasesPending`, `getImagePhaseStatuses`).
