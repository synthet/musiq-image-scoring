# API Contract Summary

REST API for the Vexlum Scoring Scoring WebUI. Base path: `/api`.

## Overview

| Category | Endpoints |
|----------|-----------|
| **Scoring** | start, stop, status, fix-db, single, fix-image |
| **Tagging** | start, stop, status, single |
| **Clustering** | start, stop, status |
| **Data Queries** | images, images/{id}, folders, stacks, stacks/{id}/images, stats |
| **Pipeline** | submit |
| **Import** | register |
| **General** | status, health, schema |
| **Jobs** | recent, {job_id} |
| **Runs** | `/api/runs/*`, `/api/queue` (see [RUNS_QUEUE_AND_RESTART.md](RUNS_QUEUE_AND_RESTART.md)) |
| **Utilities** | raw-preview, similar, duplicates/find |

**Runs queue & restart:** [RUNS_QUEUE_AND_RESTART.md](RUNS_QUEUE_AND_RESTART.md) describes how `GET /api/queue` and `JobDispatcher` relate to `jobs` rows and recovery on WebUI startup.

---

## WebSocket Events

**Endpoint:** `ws://127.0.0.1:7860/ws/updates`

**Direction:** Server → client only (push). HTTP handles request-response via `apiService.ts`; no bidirectional WebSocket commands.

**Message format:**
```json
{
  "type": "<event_type>",
  "data": { ... }
}
```

| Event Type | Description |
|------------|-------------|
| `job_started` | Batch job started (scoring, tagging, clustering, fix_db) |
| `job_progress` | Job progress update (current, total) |
| `job_completed` | Job finished (status: completed/failed) |
| `image_updated` | Image record changed in DB |
| `folder_updated` | Folder metadata changed |
| `folder_deleted` | Folder removed |
| `stack_created` | New stack created |
| `stack_updated` | Stack metadata changed |
| `stack_deleted` | Stack removed |
| `stacks_cleared` | Stacks cleared (optionally scoped to folder) |
| `image_discovered` | New image found during scan |
| `folder_discovered` | New folder found during scan |
| `folder_scanned` | Folder scan completed |
| `image_scored` | Single image scored |

---

### Utilities

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/raw-preview` | Get RAW file preview (JPEG) |

**GET /api/raw-preview** — Use query param `path` (not `file_path`):
```
GET /api/raw-preview?path=<url-encoded-file-path>
```

### fix-db (no request body)

`POST /api/scoring/fix-db` takes **no request body**. It processes all incomplete records in the database. Do not send `input_path`.

---

## Standard Response Models

### ApiResponse (operation results)
```json
{
  "success": true,
  "message": "string",
  "data": { ... }  // optional
}
```

### StatusResponse (job status)
```json
{
  "is_running": true,
  "status_message": "string",
  "progress": { "current": 0, "total": 0 },
  "log": "string",
  "job_type": "scoring|tagging|clustering|fix_db|null"
}
```

### HealthResponse
```json
{
  "status": "healthy",
  "scoring_available": true,
  "tagging_available": true,
  "clustering_available": true
}
```

---

## Clustering Endpoints (New)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/clustering/start` | Start clustering job |
| POST | `/api/clustering/stop` | Stop clustering job |
| GET | `/api/clustering/status` | Get clustering status |

### ClusteringStartRequest
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| input_path | string | No | Folder path; null = all unprocessed |
| threshold | float | No | Distance threshold (lower = stricter) |
| time_gap | int | No | Time gap (seconds) for burst grouping |
| force_rescan | bool | No | Re-cluster even if processed (default: false) |

---

## Data Query Endpoints (New)

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/images` | Paginated image query with filters |
| GET | `/api/images/{image_id}` | Single image details |
| GET | `/api/images/by-uuid/{image_uuid}` | Single image details by `images.image_uuid` |
| GET | `/api/images/by-hash/{image_hash}` | Single image details by `images.image_hash` (optional `hash_version`) |
| GET | `/api/folders` | Folder listing |
| GET | `/api/stacks` | Stacks with cover images |
| GET | `/api/stacks/{stack_id}/images` | Images in a stack |
| GET | `/api/stats` | Database statistics |

### GET /api/images — Query Parameters
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| page | int | 1 | Page number |
| page_size | int | 50 | Items per page (1–500) |
| sort_by | string | "score" | score, date, name, rating, score_general, score_aesthetic, score_technical |
| order | string | "desc" | asc, desc |
| rating | string | — | Comma-separated (e.g. "3,4,5") |
| label | string | — | Comma-separated (e.g. "Green,Blue") |
| keyword | string | — | Partial match |
| min_score_general | float | 0 | 0–1 |
| min_score_aesthetic | float | 0 | 0–1 |
| min_score_technical | float | 0 | 0–1 |
| folder_path | string | — | Filter by folder |
| stack_id | int | — | Filter by stack |

### GET /api/images — Response
```json
{
  "images": [...],
  "total": 1234,
  "page": 1,
  "page_size": 50,
  "total_pages": 25
}
```

### Image identity: `image_hash`, `hash_version`, and `image_uuid` (developer reference)

These fields serve different purposes. Do not substitute one for another when integrating.

| Mechanism | Purpose |
|-----------|---------|
| `image_hash` + `hash_version` | **Byte/payload identity** for deduplication, `GET .../by-hash/{hash}`, delete blocklists keyed by hash, clustering feature cache keys. Version distinguishes algorithms (see below). |
| `image_uuid` | **Logical identity** from EXIF / `ImageUniqueID` or a deterministic metadata fingerprint (`generate_image_uuid`); used for merge-on-import. May be absent or unstable until metadata exists — do not rely on it for indexing-time dedupe before metadata is populated. |

**`hash_version` (integer, column `images.hash_version`):**

| Value | Meaning |
|-------|---------|
| `1` | SHA-256 of the **entire file** (same semantics as legacy `compute_file_hash`). |
| `2` | SHA-256 of the **largest** embedded **preview JPEG** bytes found for TIFF-based RAW when `indexing.hash_mode` is `content_preview` and at least one candidate ≥ 64 bytes is found; see `modules/image_identity_hash.py`. |

**Version `2` discovery (Nikon-oriented, container-agnostic fallback):** candidates are merged from (in this logical order for non-`.nrw` files) **(A)** JPEG-compressed TIFF strips from every qualifying `tifffile` page, **(B)** Nikon NEF/NRW MakerNote tag `0x0011` → preview IFD → `0x0201` / `0x0202` (JPEG offset/length) with bounds checks, **(C)** the largest in-file `FFD8`…`FFD9` segment (mmap scan). The digest is **SHA-256 of the longest** JPEG blob among those candidates. For **`.nrw`**, **(C)** runs before **(A)** to avoid noisy `tifffile` failures on non-classic layouts; the **largest** blob is still chosen across **(A) ∪ (B) ∪ (C)**. HEIF-in-NEF and similar formats are out of scope for version `2` unless a new `hash_version` is introduced.

**Config:** `indexing.hash_mode` — `full_file` (always version `1`) or `content_preview` (prefer embedded JPEG for RAW; fallback to full-file `1` when no preview is found).

**Backward compatibility:** `GET /api/images/by-hash/{image_hash}` without query parameters matches on `image_hash` only (first matching row in edge cases). Clients that need a specific algorithm should pass **`hash_version`** as a query parameter (same on `/public/api/images/by-hash/...` and `/api/db/images/by-hash/...`).

**Uniqueness:** The application expects at most one `images` row per `(image_hash, hash_version)` when `image_hash` is not null. A partial unique index may enforce this in PostgreSQL (see migrations); if upgrading fails due to duplicate pairs, deduplicate rows before re-running migrations.

**Decisions (implementation):** `hash_version` is stored as a **small integer**, not a string enum. Default indexing behavior uses **`content_preview`** unless `indexing.hash_mode` is set to `full_file` (legacy byte-for-byte parity). Schema evolution uses Alembic (`hash_version` column) plus optional `scripts/python/backfill_hashes.py`; per-folder reindex is an operational choice.

### GET /api/folders — Response
```json
{
  "folders": [...],
  "count": 42
}
```

### GET /api/stacks — Query Parameters
| Param | Type | Default | Description |
|-------|------|---------|-------------|
| folder_path | string | — | Filter by folder |
| sort_by | string | "score_general" | Sort field |
| order | string | "desc" | asc, desc |

### GET /api/stacks — Response
```json
{
  "stacks": [...],
  "count": 15
}
```

### GET /api/stacks/{stack_id}/images — Response
```json
{
  "images": [...],
  "count": 8,
  "stack_id": 42
}
```

### GET /api/stats — Response (DatabaseStats)

| Field | Type | Description |
|-------|------|-------------|
| total_images | int | Total image count |
| by_rating | Record<string, number> | Counts by rating (1–5) |
| by_label | Record<string, number> | Counts by label (Red, Yellow, Green, etc.) |
| score_distribution | Record<string, number> | Buckets (e.g. "0.0-0.2", "0.2-0.4") |
| average_scores | object | general, technical, aesthetic, spaq, koniq, liqe |
| total_folders | int | Folder count |
| total_stacks | int | Stack count |
| jobs_by_status | Record<string, number> | Counts by job status |
| images_today | int | Images created today |
| error | string? | Present only when an exception occurred |

**Note:** Does not include `scored_images` or `tagged_images`.

---


| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/import/register` | Register images from folder (no scoring) |

### ImportRegisterRequest
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| folder_path | string | Yes | Folder path (Windows or WSL) |

Used by Electron when the backend is available. Path conversion applies per backend platform (see Design Notes).

---

## Pipeline Endpoint (New)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/pipeline/submit` | Submit to folder/file pipeline execution |
| POST | `/api/pipeline/phase/skip` | Mark a folder phase as skipped |
| POST | `/api/pipeline/phase/retry` | Retry a supported skipped phase |
| POST | `/api/pipeline/phase/backfill-index-meta` | Repair missing indexing/metadata status |

### PipelineSubmitRequest
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| input_path | string | Yes | File or directory path |
| operations | string[] | No | `indexing`, `metadata`, `score`, `tag`, `cluster` in execution order |
| skip_existing | bool | No | Skip images with results (default: true) |
| custom_keywords | string[] | No | For tagging |
| generate_captions | bool | No | For tagging (default: false) |
| clustering_threshold | float | No | For clustering |
| clustering_time_gap | int | No | Burst grouping gap for clustering |
| clustering_force_rescan | bool | No | Force clustering rerun |

### Pipeline Submit Behavior
- Starts the **first** operation immediately.
- For folder requests, `indexing`, `metadata`, and `score` all enqueue the scoring runner with derived `target_phases`.
- Returns `remaining_operations` in `data` for the client to chain.
- Returns `queue_position` and persisted `phase_plan` rows for folder requests.
- Electron app chains by polling status and re-submitting with the next operation.
- Single files: only `score` and `tag` supported; `cluster` requires a folder.

### Pipeline Submit Response (success)
```json
{
  "success": true,
  "message": "Pipeline queued: indexing",
  "data": {
    "job_id": 123,
    "input_path": "D:/Photos/2024",
    "current_operation": "indexing",
    "queue_position": 1,
    "phase_plan": [
      { "phase_order": 0, "phase_code": "indexing", "state": "running" },
      { "phase_order": 1, "phase_code": "metadata", "state": "pending" }
    ],
    "remaining_operations": ["metadata", "score", "tag", "cluster"]
  }
}
```

### PipelinePhaseControlRequest
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| input_path | string | Yes | Folder path |
| phase_code | string | Yes | Supported retry phases: `scoring`, `keywords`, `culling` |
| reason | string | No | Skip reason |
| actor | string | No | Caller identifier |

### PipelineBackfillRequest
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| input_path | string | Yes | Folder path to repair |

---

## GET /api/status — Extended

Now includes `clustering` runner state:

```json
{
  "scoring": { "available": true, "is_running": false, ... },
  "tagging": { "available": true, "is_running": false, ... },
  "clustering": { "available": true, "is_running": false, ... }
}
```

---

## Error Codes

| Code | Meaning |
|------|---------|
| 200 | Success |
| 400 | Bad Request (invalid path, invalid operations, etc.) |
| 404 | Not Found (image, job, etc.) |
| 500 | Internal Server Error |
| 503 | Service Unavailable (runner not initialized) |

---

## Design Notes

- **Data query endpoints** delegate to existing `db.py` functions; no new DB code.
- **Stats endpoint** reuses `get_database_stats()` from the MCP server module.
- All endpoints follow existing patterns: Pydantic models, `ApiResponse` wrapper, rate limiting, path validation.
- **Path conversion:** When the backend runs on Linux (WSL), Windows paths are converted to WSL via `utils.convert_path_to_wsl`. When the backend runs natively on Windows, paths are kept as-is.
