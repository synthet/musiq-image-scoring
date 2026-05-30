# Image embeddings (MobileNetV2, Postgres, backfill)

## What is stored

- **Primary (PostgreSQL):** Registry table **`embedding_spaces`** plus **`image_embeddings`** — one row per `(image_id, embedding_space_id)` with `embedding vector(1280)`, optional `model_version`, and an HNSW index for cosine search. The default space code is **`mobilenet_v2_imagenet_gap`** (see [`modules/embedding_spaces.py`](../../modules/embedding_spaces.py)).
- **Legacy column (deprecated):** **`images.image_embedding`** — optional dual-write while the column exists; set **`database.write_legacy_image_embedding_column`** to `false` to write only `image_embeddings`. Alembic **0024** drops the column; see [IMAGE_EMBEDDING_COLUMN_DEPRECATION.md](../planning/database/IMAGE_EMBEDDING_COLUMN_DEPRECATION.md).
- **Firebird (Electron gallery):** Single BLOB on **`images.image_embedding`** only; multi-space storage is **PostgreSQL-first** until the gallery migrates off Firebird (see [DB_VECTORS_REFACTOR.md](../planning/database/DB_VECTORS_REFACTOR.md)).
- **Model:** TensorFlow Keras **MobileNetV2**, ImageNet weights, `include_top=False`, global average pooling → **1280** floats.
- **Semantics:** Coarse **visual similarity** features for clustering, near-duplicate-style retrieval, tag propagation neighbors, and similar-image search. They are **not** CLIP text–image aligned embeddings.

## When embeddings are written

1. **Culling phase (clustering)** — [`modules/clustering.py`](../../modules/clustering.py) `ClusteringEngine.extract_features()` persists batches with `db.update_image_embeddings_batch()` (PostgreSQL also upserts **`image_embeddings`** for the default space when the registry row exists). Algorithm/model identity is tracked in code as `CLUSTER_VERSION` in that module; callers may pass `model_version=` into the batch API to persist it on `image_embeddings`.
2. **On demand** — [`modules/similar_search.py`](../../modules/similar_search.py) may compute and persist a single embedding via `ClusteringEngine` if an image is queried and `image_embedding` is null.

## Backfill images missing embeddings

Run in **WSL** with **`~/.venvs/tf`** (same as the web UI), with paths to thumbnails or originals resolvable from WSL.

**Canonical Windows one-launcher:**

```text
scripts\maintenance\run_populate_embeddings.bat
```

Optional arguments are passed through to Python, for example:

```text
run_populate_embeddings.bat --dry-run
run_populate_embeddings.bat --limit 500
run_populate_embeddings.bat --folder "D:\Photos\Trip"
run_populate_embeddings.bat --resume-after-id 12345
```

**Direct Python (WSL):**

```bash
python scripts/maintenance/populate_missing_embeddings.py [--dry-run] [--limit N] [--folder PATH] [--batch-size N] [--resume-after-id ID]
```

**Legacy launcher name:** `run_populate_missing_embeddings.bat` calls the same script (backward-compatible).

## Schema: column on `images` vs registry + `image_embeddings`

On **PostgreSQL**, the app now uses:

- **`embedding_spaces`** — canonical codes and dimensions (`dim` documents intent; the physical `vector(N)` column is still fixed per table).
- **`image_embeddings`** — stores vectors for each `(image_id, embedding_space_id)` with **`UNIQUE(image_id, embedding_space_id)`** and HNSW on **`image_embeddings.embedding`**.
- **`images.image_embedding`** — **deprecated** on Postgres (removed by migration 0024); use **`image_embeddings`** for all new work.

For a **single** embedding type, a column on `images` alone is enough; the project is in an **expand-contract** phase: both the column and `image_embeddings` are populated for the default MobileNet space.

**pgvector rule (unchanged):** each `vector(N)` has a **fixed N**. A **512-d** CLIP space needs a **different** column or table — not another row in the current `image_embeddings.embedding` column (1280). See [DB_VECTORS_REFACTOR.md](../planning/database/DB_VECTORS_REFACTOR.md) worklog and follow-ups.

**Upgrade:** run Alembic revision **`0004`** (`migrations/versions/0004_embedding_spaces_image_embeddings.py`) on existing databases; `init_db()` on greenfield Postgres creates the same objects.

## Checklist for additional models (e.g. CLIP)

If you add another stored vector, define up front:

| Field | Example |
|-------|---------|
| Model identity | `mobilenet_v2_imagenet_gap`, `clip_vit_b32_image` |
| Dimension `N` for `vector(N)` | 1280 vs 512, etc. |
| Semantic use | CNN visual vs CLIP image tower vs text |
| Version | Tie to `CLUSTER_VERSION`, HF revision, or weights hash |
| Indexes | Separate HNSW (or IVFFlat) per query pattern |
| API / callers | Which endpoints and MCP tools read which space |

Treat a new space as **not interchangeable** with MobileNet embeddings without migration, reindex, and caller updates.

### Registered spaces (as of Alembic `0012`)

| Space code | Dim | Table | Producer (piggyback phase) | Model version (default) |
|---|---|---|---|---|
| `mobilenet_v2_imagenet_gap` | 1280 | `image_embeddings` | `modules/clustering.py` (culling / indexing) | `CLUSTER_VERSION` |
| `clip_vit_b32_image` | 512 | `image_embeddings_512` | `modules/tagging.py::KeywordScorer.predict` (keywords phase) | `openai/clip-vit-base-patch32` |
| `bioclip_2_image` | 768 | `image_embeddings_768` | `modules/bird_species.py::BioCLIPClassifier.classify` (bird-species phase) | `hf-hub:imageomics/bioclip-2` |
| `blip_vit_b16_image` | 768 | `image_embeddings_768` | `modules/tagging.py::CaptionGenerator.generate` (keywords phase, captions enabled) | `Salesforce/blip-image-captioning-base` |
| `openclip_l14_laion2b_image` | 768 | `image_embeddings_768` | `modules/embedding_extractors.py` (opt-in / backfill) | `ViT-L-14/laion2b_s32b_b82k` |
| `openai_clip_vit_l14_image` | 768 | `image_embeddings_768` | `modules/embedding_extractors.py` (opt-in / backfill) | `ViT-L-14-quickgelu/openai` |
| `dinov2_reg_base_image` | 768 | `image_embeddings_768` | `modules/embedding_extractors.py` (opt-in / backfill) | `vit_base_patch14_dinov2.lvd142m` |
| `siglip2_base_image` | 768 | `image_embeddings_768` | `modules/embedding_extractors.py` (opt-in / backfill) | `google/siglip2-base-patch16-224` |

The last four are **optional culling towers** (registered by migration `0029`,
not generated by default). They are produced on demand by
`modules/embedding_extractors.py` — listed in `embeddings.culling_spaces` and
backfilled via `scripts/backfill_culling_embeddings.py` — and become selectable
per two-level culling level. See
[two-level-culling.md](../features/planned/embeddings/two-level-culling.md#selectable-embedding-spaces-integrating-new-culling-models)
and [the culling model recommendation](../reports/CULLING_MODEL_RECOMMENDATION_2026-05-29.md).

All these spaces share the same keyed-fact-table shape (`image_id`, `embedding_space_id`, `embedding vector(N)`, `model_version`, `updated_at`) with a unique key on `(image_id, embedding_space_id)` and an HNSW cosine index on `embedding`. Dimension routing is centralized in `modules/db._pg_embedding_table_for_dim()`.

### Adding a new space

1. Register the code in `modules/embedding_spaces.SPACE_DIMS` with the correct dim.
2. If the dim is not already served by `image_embeddings`, `image_embeddings_512`, or `image_embeddings_768`, create a new per-dim table following the pattern in migration `0012` and extend `_pg_embedding_table_for_dim()`.
3. Add an Alembic migration that inserts the registry row and any new DDL; mirror in `modules/db_postgres._init_db_transaction()` so greenfield installs match.
4. Extract the vector inside the phase that already runs the model (see `modules/embeddings_extract.py` for templates) and flush via `db.update_image_embeddings_batch_for_space(code, rows)`.
5. Wire consumers (`similar_search.search_similar_images(..., embedding_space=code)`, MCP `search_similar_images` / `get_embedding_stats`) when the space becomes useful for retrieval.

### Config flags

The `embeddings` section in `config.json` gates per-model persistence and pins the `model_version` string stored on each row:

```json
"embeddings": {
  "persist_clip_image": true,
  "persist_blip_image": true,
  "persist_bioclip_image": true,
  "model_versions": {
    "clip_vit_b32_image": "openai/clip-vit-base-patch32",
    "blip_vit_b16_image": "Salesforce/blip-image-captioning-base",
    "bioclip_2_image": "hf-hub:imageomics/bioclip-2"
  }
}
```

### Operational notes (gotchas)

- **`get_embedding_space_id` caches positive hits only.** A miss (Postgres engine not active, registry row not yet seeded by Alembic, or transient DB error) does *not* poison the cache; the next call performs a fresh DB lookup. A long-running webui/runner started before a `0012`-style migration runs will recover automatically once the migration completes.
- **`BLIP_768` only fills when captions are generated.** `CaptionGenerator.generate(extract_embedding=True)` is the producer, and the runner only sets `extract_embedding=True` when `generate_captions=True`. Tagging-only jobs leave `image_embeddings_768` empty by design — BLIP's vision tower is only worth running when a caption is already needed.
- **`BIOCLIP_768` only fills during bird-species jobs.** `BirdSpeciesRunner` is the only writer. Empty rows for `bioclip_2_image` are usually "no bird-species job ran", not a defect. Alembic `0026` corrects the registry if `bioclip_2_image` was still listed as 512-d (BioCLIP 2 is ViT-L/14, not ViT-B/32).
- **Shared `tagging_engine` path does not extract embeddings yet.** `TaggingRunner(tagging_engine=...)` skips the `_persist_tagging_embeddings` call (the engine doesn't surface `last_image_embedding`). Production call sites use `TaggingRunner()` with no engine and persist correctly; the runner emits a one-time `WARNING` per instance if persist flags are enabled on the engine path so the gap is discoverable.
- **Persist failures log at `WARNING`.** Earlier code logged at `DEBUG`, hiding real upsert errors at default log levels. If an `image_embeddings_*` table is mysteriously empty, `grep "embedding upsert failed\|embedding persist failed" webui.log` first.

## Related code

- [`modules/embedding_spaces.py`](../../modules/embedding_spaces.py) — default space code, `get_default_embedding_space_id()`
- [`modules/clustering.py`](../../modules/clustering.py) — feature extraction and culling persistence
- [`modules/similar_search.py`](../../modules/similar_search.py) — similarity search, `EMBEDDING_DIM`; Postgres queries join `image_embeddings`
- [`modules/db.py`](../../modules/db.py) — `update_image_embedding(s)`, `get_images_missing_embeddings`, `_postgres_has_default_embedding_sql`, etc.
- [`modules/db_postgres.py`](../../modules/db_postgres.py) — DDL for `images`, `embedding_spaces`, `image_embeddings`, HNSW indexes
- [`migrations/versions/0004_embedding_spaces_image_embeddings.py`](../../migrations/versions/0004_embedding_spaces_image_embeddings.py) — Alembic upgrade for registry + backfill
- [`scripts/maintenance/populate_missing_embeddings.py`](../../scripts/maintenance/populate_missing_embeddings.py) — backfill CLI
- [`docs/planning/database/DB_VECTORS_REFACTOR.md`](../planning/database/DB_VECTORS_REFACTOR.md) — plan, worklog, follow-ups
