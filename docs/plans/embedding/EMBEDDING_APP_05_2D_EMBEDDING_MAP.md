# 05 - 2D Embedding Map (Visual Collection Explorer)

*Part of [Possible Applications of image_embedding](EMBEDDING_APPLICATIONS.md).*

## Status (2026-04-24)

**Phase 0 — done.** `modules/projections.py::compute_embedding_map` (UMAP / t-SNE, L2-normalize, min-max scale) and `GET /api/embedding_map` (folder, method, sample_limit, n_neighbors, min_dist, refresh, disk-cached) are implemented and live for the 1280-d MobileNet space.

**Open work — see "Roadmap" below.** Multi-space support, optional PCA pre-step, HDBSCAN clustering, persistent projection storage, and a similar-image side panel are all phased follow-ups, not part of the original v1 scope.

## Goal

Provide an interactive 2D map of the image library where spatial proximity reflects visual similarity.

## Why this matters

A map-based view enables fast exploration of large collections, cluster discovery, and gap analysis that are difficult in list/gallery-only interfaces.

## Proposed behavior

Project 1280-d embeddings to 2D using UMAP (or t-SNE fallback), then render a pan/zoom scatter with thumbnails and metadata overlays.

User capabilities:

- zoom into dense clusters,
- filter by folder/label/rating/date,
- click points to open image details,
- run "find similar" from selected point.

## Integration points

- `modules/api.py`
  - Add endpoint: `GET /api/embedding_map`.
- `modules/db.py`
  - Reuse `get_embeddings_for_search(folder_path=...)`.
- UI layer
  - New tab or section in existing stacks workflow.

## API contract (proposal)

Request params:

- `folder_path` (optional)
- `method` (`umap|tsne`, default `umap`)
- `refresh` (bool, default `false`)
- `sample_limit` (optional)

Response:

- `points`: array of `{image_id, x, y, thumbnail_path, label, rating, score_general}`
- `meta`: `{count, method, computed_at, cache_key}`

## Computation pipeline

1. Load embeddings and image metadata.
2. Normalize vectors.
3. Fit dimensionality reduction model.
4. Scale 2D coordinates to viewport space.
5. Cache results by dataset fingerprint.

## Caching strategy

- Key by `(folder_path, embedding_count, newest_updated_at, method, params)`.
- Store map output on disk to avoid expensive recompute.
- Invalidate on re-clustering or mass embedding updates.

## Configuration

- `embedding_map.enabled` (bool, default `false`)
- `embedding_map.method` (`umap`, default)
- `embedding_map.n_neighbors` (int, default `30`)
- `embedding_map.min_dist` (float, default `0.1`)
- `embedding_map.max_points` (int, default `50000`)

## Dependencies

- Primary: `umap-learn`
- Optional fallback: scikit-learn t-SNE

## Edge cases

- Too few points: skip projection and use simple layout.
- Too many points: server-side sampling or level-of-detail aggregation.
- Missing thumbnails: render neutral marker and lazy-load fallback.

## Performance notes

- Projection can be expensive for very large collections.
- Prefer async compute job for large inputs and return cached/partial status.

## Validation plan

- API tests for schema and pagination/sampling.
- UI tests for zoom/filter/selection behaviors.
- Performance profiling on representative large datasets.

## Success metrics

- Acceptable load time for folder-scale views.
- Increased discovery of related images (measured via click-through to detail/similar actions).
- Positive usability feedback compared to baseline gallery browsing.

---

## Roadmap — multi-space + clustering (post-v1)

The original v1 above shipped for the default 1280-d MobileNet space only. With Alembic `0012` adding 512-d (CLIP, BioCLIP) and 768-d (BLIP) per-dim fact tables (see [DB_VECTORS_REFACTOR.md](../database/DB_VECTORS_REFACTOR.md)), the natural next steps are:

### Phase 1 — multi-space + PCA on the existing endpoint (✅ shipped 2026-04-25)

- **`modules/projections.compute_embedding_map`** accepts `embedding_space=None` (defaults to `DEFAULT_EMBEDDING_SPACE_CODE`) and `pca_dim=None` (auto: 50 for source dim ≥ 1280, off below; pass `0` to disable explicitly).
- **New helper `modules/projections_db.get_embeddings_with_metadata_for_space(space_code, …)`** — delegates to `db.get_embeddings_with_metadata` for the default space (so the legacy-column fallback still applies) and reads straight from the per-dim fact table chosen by `_pg_embedding_table_for_dim` for non-default spaces. Lives in its own module per CLAUDE.md guidance to avoid growing `db_legacy.py`. Postgres-only for non-default spaces.
- **`GET /api/embedding_map`** accepts `space_code` and `pca_dim`; both bake into the disk-cache key so a CLIP map and a MobileNet map don't clobber each other. Unknown `space_code` returns `meta.error == "unknown_embedding_space"`.
- **REST parity for similarity:** `GET /api/similarity/search` accepts `embedding_space`, forwarded to `search_similar_images`. New endpoint `GET /api/images/{image_id}/similar` (k-NN; deliberately distinct from `/{id}/neighbors`, which is prev/next gallery navigation).
- Tests in `tests/test_api_embedding_map.py` cover non-default routing through `projections_db`, PCA on/off/explicit, unknown space, the new `/similar` endpoint (happy + 404), and cache-key separation.

### Phase 2 — persistent projections + HDBSCAN (opt-in)

Only ship if disk cache + recompute proves to be the bottleneck under real usage — disk cache already prevents per-request recompute.

- **Alembic `0013_image_embedding_projections.py`** — `image_embedding_projections (image_id, embedding_space_id, projection_method, projection_version, x, y, z, cluster_id, updated_at)` with `UNIQUE(image_id, embedding_space_id, projection_method, projection_version)`. Mirror DDL in `db_postgres._init_db_transaction()`.
- **`projection_version` is a deterministic hash** of `(method, n_neighbors, min_dist, pca_dim, metric, source_count_bucket)`. Never write rows under the same version with different inputs.
- **HDBSCAN** (`min_cluster_size=10`, configurable) computed over the **PCA-50 representation** (more robust than 2D coords). Add `hdbscan` to `requirements.txt`; verify install in `~/.venvs/tf` before merge.
- **`modules/projection_runner.py`** — one-shot job (not a pipeline phase) enqueued via `job_dispatcher`. Memory ceiling, batched fit/transform for >10k vectors, resume-safe via `job_phases`.
- **Endpoint behavior:** `GET /api/embedding_map` reads from the table when `(space_code, method, version)` matches; falls back to compute-on-demand and writes back when `?persist=true`.

### Phase 3 — UI atlas (frontend project)

Belongs in [image-scoring-gallery](https://github.com/synthet/image-scoring-gallery) or as a new tab in the backend's React SPA at `/ui/`.

- Deck.gl ScatterplotLayer for ≥10k points; Plotly for smaller views as a fallback.
- Color-by selector wired to `score_general / score_aesthetic / cluster_id / embedding_space / model_version / camera`.
- Side panel: selected image preview + metadata + thumbnail grid of `GET /api/images/{id}/similar`.
- Filters: folder, score range, date, camera, model version, "show only cluster N", "hide noise (-1)".
- Space selector sourced from a small new `GET /api/embedding_spaces` endpoint that surfaces the registry rows.

### Decisions called out (don't defer to implementation time)

1. **PCA on by default for ≥1280-d**, off below. Override via `pca_dim=0`.
2. **`space_code` is the wire identifier**, not `embedding_space_id`. IDs are local to the DB; codes are stable strings the frontend can hard-code.
3. **`projection_version` includes a hash of all inputs.** Ship a `version_for(method, params, source_count)` helper so callers never construct version strings by hand.
4. **HDBSCAN over PCA-50, not 2D UMAP.** Higher-D representation gives more meaningful clusters (per upstream research and consensus in the literature).
5. **DB-backed projections are opt-in via `?persist=true`.** Default stays disk-cached.
6. **Phase 1 ships standalone.** It is genuinely useful by itself; do not gate on phase 2.

### Out of scope (call out to avoid creep)

- 3D projections (`z` column) — reserve in schema, don't compute.
- Cross-space projections (CLIP and MobileNet on the same atlas) — mathematically incoherent.
- Streaming / incremental UMAP — only if a real product need surfaces.
- Firebird parity — multi-vector remains Postgres-only until the gallery migrates.

### Naming collisions to avoid

- `GET /api/images/{id}/neighbors` is taken (prev/next nav). Use `/similar` or `/knn`.
- `db.get_image_neighbors` returns `(prev_id, next_id)`. Don't repurpose for k-NN helpers.
- `GET /api/embedding_map` is the existing path. Don't introduce `/api/embeddings/map`.
