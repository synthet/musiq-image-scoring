# Clustering, culling, and stacks

**Purpose:** Group similar images into **stacks** (similarity clustering / “culling” stage) so operators can compare picks and rejects.

**User-visible behavior:** Clustering jobs over a folder (or full library) with tunable threshold/time-gap; stack listing and per-stack image membership in API and UIs.

**Primary code paths:** `modules/clustering.py`, clustering runner, stack tables via `modules/db*.py`.

**Main HTTP API (prefix `/api`):**

- `POST /api/clustering/start`, `POST /api/clustering/stop`, `GET /api/clustering/status`
- `GET /api/stacks`, `GET /api/stacks/{stack_id}/images` (and related image query filters by `stack_id` on `GET /api/images`)

**Related docs:** [CULLING_FEATURE](../../technical/CULLING_FEATURE.md) · [STACKS_MANUAL_MANAGEMENT](../../technical/STACKS_MANUAL_MANAGEMENT.md) · [planning/refactoring/STACK_CULLING_REFACTOR_PLAN.md](../../planning/refactoring/STACK_CULLING_REFACTOR_PLAN.md)

## Tuning (`config.json` → `clustering`)

Clustering uses **two independent knobs** (neither is “how many images per stack”):

| Key | Meaning |
|-----|--------|
| **`default_threshold`** | **Visual** similarity — cosine distance cutoff for agglomerative clustering *inside each time batch* (lower = stricter). |
| **`default_time_gap`** | **Temporal** grouping in **seconds**. All images in a folder pass are sorted by capture time. Walk the timeline: if the gap between **two consecutive** shots is **greater than** this value, a **new batch** starts. Visual similarity is only computed **between images in the same batch**. Example: `3` keeps rapid sequences together; `120` allows shots up to two minutes apart to stay in one batch. |

API / job payloads mirror these as `threshold` / `time_gap` on clustering start and as `clustering_threshold` / `clustering_time_gap` on orchestrated runs where applicable.

### Heal Culling — time-cohesive “no stacks” folders

`get_phase_incomplete_sql('culling')` (used by **Heal Culling** in `workflow_healing`) can flag images in folders where:

- at least **two** images exist, **none** have `stack_id` set,
- each row has **pick/reject** (`cull_decision`), a **content hash**, and **default-space Mobilenet** embeddings,
- the folder’s **capture-time span** (min→max of EXIF date or `created_at`) is **≤ `(n-1) * default_time_gap`**.

That matches “these frames could have been one clustering time batch but never formed stacks” (e.g. tune `default_threshold` / re-run). Disable via `clustering.heal_folder_cohesion_candidates: false` in `config.json`.

## Troubleshooting / history

**2026 data-path fix (shipped):** Clustering reads folder images via `get_images_by_folder()` (Postgres: `SELECT i.*`; Firebird: explicit columns including `thumbnail_path`, `score_general`, `burst_uuid`). `modules/clustering.py` uses safe `r.get('score_general')` access and logs when zero new stacks are created after processing images — avoids KeyError aborts that left culling "done" with no stacks.
