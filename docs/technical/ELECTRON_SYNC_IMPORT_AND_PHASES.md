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

1. **Scoring runner short-circuits when given an explicit `image_ids` list** — [#156](https://github.com/synthet/image-scoring-backend/issues/156). `job_phases.scoring` was marked **`completed`** in ~3 s with `images_in_scope = 0, images_processed = 0`, and no **`image_phase_status`** rows were created for `scoring`. The 733 ids in `jobs.queue_payload.resolved_image_ids` were all left with `score_general IS NULL`. G5 mitigates the contract side (rows now exist as `not_started`), but the runner itself still needs to enumerate work from those rows or from the explicit ids list.

2. **Culling runner exhibits the same short-circuit** — [#157](https://github.com/synthet/image-scoring-backend/issues/157). `job_phases.culling` completed in seconds with zero scope and zero processed; no images received a `stack_id`. Likely cascades from #156 (clustering depends on scoring/embeddings).

3. **`job_phases` counters are not flushed during a phase, only at finalize** — [#158](https://github.com/synthet/image-scoring-backend/issues/158). `images_in_scope` / `images_processed` / `images_skipped` stay at 0 for the entire active phase and only update when the phase completes via `ReportCollector.finalize()` (`modules/report_collector.py`). The Runs UI faithfully shows `0 / 0 work items` during the active phase even when work is happening — confirmed for run 2365 metadata phase, which had 86 → 600 → 733 `image_phase_status` rows transitioning while `job_phases.metadata.images_processed` stayed 0 until the very end.

## Related

- **[AGENT_COORDINATION.md](AGENT_COORDINATION.md)** — cross-repo contracts.
- **[RUNS_WALKTHROUGH.md](RUNS_WALKTHROUGH.md)** — runs and queue behavior.
- **Gallery** — `electron/scheduleProcessing.ts`, `electron/db.ts` (`markImageIndexingPhaseDone`, `markImagePhasesPending`, `getImagePhaseStatuses`).
