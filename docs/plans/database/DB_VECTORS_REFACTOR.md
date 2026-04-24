---
name: DB normalization refactor
overview: Primary goal — store **multiple embedding/vector types** (different models, dimensions, and semantics) in PostgreSQL with pgvector, while keeping a safe migration path from today's single `images.image_embedding` column. Secondary (optional) track — hybrid-3NF Phase 4 and broader score/job normalization from the earlier plan.
todos:
  - id: vec-design
    content: Define embedding kind registry (codes, dims, semantics); choose physical pgvector pattern (per-dimension table vs few nullable columns); document in EMBEDDINGS.md
    status: completed
  - id: vec-schema
    content: Alembic migration + db_postgres.py init_db — new tables/columns, HNSW (or IVFFlat) per stored vector column, UNIQUE(image_id, kind) or one row per kind table
    status: completed
  - id: vec-migrate
    content: Backfill existing MobileNet vectors from images.image_embedding into new storage; keep legacy column during transition (dual-read or VIEW)
    status: completed
  - id: vec-api
    content: Extend modules/db.py (batch/single upsert, fetch by kind, missing-embedding queries); Postgres write paths for embedding columns
    status: completed
  - id: vec-callers
    content: Wire modules/clustering.py, similar_search.py, API/MCP embedding tools to explicit model_key; no silent mixing of vector spaces
    status: completed
  - id: vec-firebird
    content: If parity required — Firebird DDL + BLOB layout per kind or document Postgres-only multi-vector until Electron migrates
    status: completed
  - id: norm-deferred
    content: (Optional) Phase 4 metadata/keywords cutover, image_scores fact table, job_scopes — see appendix in plan body
    status: pending
isProject: false
---

# DB refactor plan — multi-type vectors (primary) + optional normalization (secondary)

## Primary goal — different types of vectors

Today the system assumes **one** visual embedding per image: `images.image_embedding` as `vector(1280)` (MobileNetV2 GAP) in Postgres and a float32 BLOB in Firebird. See [EMBEDDINGS.md](../../technical/EMBEDDINGS.md).

**Product goal:** Persist **several non-interchangeable** vector spaces (e.g. current CNN visual features, future CLIP image tower, optional text embeddings keyed by image+caption version) with:

- Stable **model identity** (`model_key` / `embedding_kind`) and **dimension** `N`
- **Version** or weights identity for invalidation/recompute
- **Separate ANN indexes** per space (pgvector HNSW is per column; spaces with different `N` cannot share one `vector` column)

### pgvector constraint (drives schema shape)

A single column is typed `vector(N)` with **fixed N**. You cannot store 1280-d and 512-d vectors in the same column. Practical patterns:


| Pattern                                                  | When to use                                                                                                                                                                                                       |
| -------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A. Few known kinds**                                   | Add nullable columns on `images`, e.g. `embedding_visual vector(1280)`, `embedding_clip_image vector(512)` — each with its own HNSW index. Simple queries, no join.                                               |
| **B. Catalog + one physical table per dimension family** | e.g. `image_embeddings_1280(image_id, kind, vector(1280), model_version, updated_at)` with `UNIQUE(image_id, kind)` — multiple models sharing dim (rare) or one row per kind with CHECK on allowed `kind` values. |
| **C. One table per kind**                                | `image_emb_mobilenet_v2(...)`, `image_emb_clip_vit_b32(...)` — clearest indexes and migrations; more DDL when adding kinds.                                                                                       |


Recommended starting point: **(A) or (C)** — avoid a generic "EAV with one bytea vector" that loses pgvector indexing.

Add a small **registry table** (e.g. `embedding_spaces`: `code`, `dim`, `description`, `active`) so the app and migrations agree on valid kinds and dimensions.

### Migration / expand-contract

1. Introduce new storage (chosen pattern) and registry row for existing MobileNet space (e.g. `mobilenet_v2_imagenet_gap`, dim 1280).
2. **Backfill** from `images.image_embedding` into the new structure.
3. **Dual-read window:** similarity search and clustering read from new storage with fallback to legacy column.
4. **Dual-write:** all writers update new storage + legacy column until callers are switched.
5. **Drop or null legacy column** after one release cycle and update [EMBEDDINGS.md](../../technical/EMBEDDINGS.md).

### Code touchpoints (non-exhaustive)

- [modules/db_postgres.py](../../../modules/db_postgres.py) — DDL, `POSTGRES_APP_TABLES`, HNSW indexes
- [migrations/versions/](../../../migrations/versions/) — new revision(s)
- [modules/db.py](../../../modules/db.py) — `update_image_embedding(s)`, `get_embeddings_for_search`, `get_images_missing_embeddings`, Postgres embedding write paths (see CHANGELOG notes)
- [modules/clustering.py](../../../modules/clustering.py) — `CLUSTER_VERSION` / model identity when persisting
- [modules/similar_search.py](../../../modules/similar_search.py) — `EMBEDDING_DIM`, query space selection
- [scripts/maintenance/populate_missing_embeddings.py](../../../scripts/maintenance/populate_missing_embeddings.py) — `--kind` or default kind
- API / MCP — any tool that assumes a single embedding column must take or default `embedding_kind`

### Firebird / Electron

Multi-vector may be **Postgres-first**: Firebird can keep a single BLOB for the legacy gallery path until Phase 4 Postgres migration, or gain a parallel `IMAGE_EMBEDDINGS` table with `(image_id, kind, blob)` without pgvector. Document the chosen parity rule in the implementation ticket.

### Success criteria (vectors)

- Adding a second kind (e.g. 512-d) does not require altering the 1280-d column's type.
- Similarity and clustering APIs explicitly select **which space**; no cosine search across mismatched dimensions.
- P95 similarity queries remain acceptable with **one HNSW index per queried column/table**.
- [EMBEDDINGS.md](../../technical/EMBEDDINGS.md) checklist (model identity, dim, semantics, version, indexes, callers) is filled for each stored space.

### Gallery (Electron) Compatibility

The `image-scoring-gallery` (Electron) application is a major consumer of the `images` table.

- **Vector Refactor**: No immediate impact, as Electron does not query embeddings directly.
- **Normalization (A0, A1)**: **High Risk.** Electron relies on denormalized `keywords` and `score_*` columns in `images` (see [DATABASE_REFACTOR_ANALYSIS.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/technical/DATABASE_REFACTOR_ANALYSIS.md) in **image-scoring-gallery**.)
- **Mitigation**: Any removal of legacy columns in `images` must be preceded by a **VIEW** that maintains the legacy schema interface for the gallery.

---

## As implemented (PostgreSQL) — registry + `image_embeddings`

Physical storage follows a **registry + keyed fact table** (closest to plan **Pattern B** for a single 1280-d family), not separate physical tables per model:

| Object | Role |
|--------|------|
| `embedding_spaces` | Registry: `code`, `dim`, `description`, `active`; seeded with `mobilenet_v2_imagenet_gap` (1280). |
| `image_embeddings` | `(image_id, embedding_space_id)` unique; `embedding vector(1280)`; optional `model_version`, `updated_at`; HNSW on `embedding`. |
| `images.image_embedding` | **Legacy / dual-write** column; readers use `COALESCE(ie.embedding, i.image_embedding)` where applicable. |

- **DDL / greenfield:** [`modules/db_postgres.py`](../../modules/db_postgres.py) `init_db()`.
- **Upgrade path:** Alembic [`migrations/versions/0004_embedding_spaces_image_embeddings.py`](../../migrations/versions/0004_embedding_spaces_image_embeddings.py) (creates tables, index, seed, backfill from `images.image_embedding`).
- **Constants / space id cache:** [`modules/embedding_spaces.py`](../../modules/embedding_spaces.py).

**Adding a second dimension (e.g. 512-d CLIP)** still requires a **new `vector(N)` column or new table** (pgvector rule); the current `image_embeddings.embedding` is fixed at 1280.

---

## Worklog

| Date | Area | Notes |
|------|------|--------|
| 2026-04-01 | Schema | `embedding_spaces` + `image_embeddings` added in `db_postgres.py`; `POSTGRES_APP_TABLES` extended for truncate order. |
| 2026-04-01 | Migration | Revision `0004` — create registry + junction table, HNSW on `image_embeddings.embedding`, seed row, backfill from `images.image_embedding`, `SET NOT NULL` on `embedding`. |
| 2026-04-01 | `db.py` | `_pg_default_embedding_space_subquery_sql`, `_postgres_has_default_embedding_sql`; dual-write in `update_image_embedding` / `update_image_embeddings_batch` (optional `model_version`); dual-read via `LEFT JOIN` + `COALESCE` for getters, `get_embeddings_for_search`, `get_embeddings_with_metadata`, tag-propagation queries; Postgres-specific `_get_images_missing_embeddings_pg`; `list_folder_paths_with_missing_keywords` embed clause on Postgres. |
| 2026-04-01 | `similar_search.py` | Postgres path uses `COALESCE(ie.embedding, i.image_embedding)` with join to `image_embeddings` for search / counts / near-duplicate SQL. |
| 2026-04-03 | Docs | Worklog + EMBEDDINGS.md update; reconciled plan text with implemented Pattern B–style layout (removed obsolete Pattern C table-per-kind spec). |
| 2026-04-23 | Schema | Alembic revision `0012` — new per-dimension fact tables `image_embeddings_512` and `image_embeddings_768` (same shape as `image_embeddings`), HNSW cosine indexes, and seeded `embedding_spaces` rows for `clip_vit_b32_image` (512), `bioclip_2_image` (512), and `blip_vit_b16_image` (768). Mirrored DDL + seed in `modules/db_postgres._init_db_transaction()`; extended `POSTGRES_APP_TABLES` for truncate order and post-truncate re-seed. |
| 2026-04-23 | `db.py` | Added `_pg_embedding_table_for_dim(dim)` (1280/512/768 → table), `update_image_embeddings_batch_for_space(space_code, rows)` with dim-vs-registry validation and `ON CONFLICT (image_id, embedding_space_id) DO UPDATE`, and `get_images_missing_embedding_for_space(space_code, folder_path, limit)`. Existing 1280-d writers unchanged. `modules/embedding_spaces.py` gained `SPACE_DIMS` and a cached `get_embedding_space_id(code)` helper. |
| 2026-04-23 | Piggyback | New `modules/embeddings_extract.py` with pure L2-normalizing helpers for CLIP (`image_embeds`), BLIP (`vision_model.pooler_output`), and BioCLIP (`encode_image`). `KeywordScorer.predict`, `CaptionGenerator.generate(extract_embedding=...)`, and `BioCLIPClassifier.classify` now capture `last_image_embedding`; `TaggingRunner` and `BirdSpeciesRunner` flush via `update_image_embeddings_batch_for_space` in best-effort try/except gated by the new `embeddings.persist_*` config flags. `model_version` is read from `embeddings.model_versions.*`. |
| 2026-04-23 | Consumers | `modules/similar_search.search_similar_images(..., embedding_space=None)` dispatches to a Postgres-only helper that reads from the per-dim table. MCP `search_similar_images` forwards the new param; MCP `get_embedding_stats` accepts `embedding_space` and, when unset, also returns a `per_space` coverage breakdown. |
| 2026-04-23 | Tests | `tests/test_postgres_integration.py` asserts the two new tables, seeded registry rows, HNSW indexes, unique constraints, and upsert + dim-validation semantics. New `tests/test_embeddings_multi_space.py` covers the pure extractors, `_pg_embedding_table_for_dim` routing, registry-mismatch `ValueError`, non-Postgres no-op, and the `TaggingRunner._persist_tagging_embeddings` flag gating with mocks. |

### Follow-ups (completed)

✓ **`modules/mcp_server.py` `get_embedding_stats`** — Uses `_postgres_has_default_embedding_sql()` + join to `image_embeddings` on Postgres for accurate stats (lines ~1005–1029).

✓ **`modules/clustering.py`** — Passes `model_version=CLUSTER_VERSION` to `update_image_embeddings_batch()` (line ~707).

✓ **`repair_culling_ips_failed_has_data`** / **`get_image_tag_propagation_focus`** — Both use `COALESCE` + join to `image_embeddings` on Postgres paths (db.py ~7186–7215, ~8007–8018).

### Remaining optional work

- **Tests:** `tests/test_postgres_integration.py` — optionally assert presence of `embedding_spaces` / `image_embeddings` alongside core tables.
- **Scripts:** `populate_missing_embeddings.py` — optional CLI `--embedding-space` for future non-default spaces.
- **Cleanup:** Remove any leftover one-off patch scripts under `tools/` used during bring-up (e.g. `run_vec.py`, `vec_apply.py`) if still present.

---

## Appendix — broader schema normalization (deferred / optional)

The following was the **previous** aggressive normalization scope; it remains valid as a **separate track** after or in parallel with vector work where team capacity allows.

### A0 — Baseline (Phase 4 keywords/metadata)

- [NEXT_STEPS.md](NEXT_STEPS.md): validation, perf gates, deprecate redundant `images.keywords` / related writable dupes
- `electron/db.ts` (image-scoring-gallery repo): keyword `LIKE` → normalized `EXISTS` / `keywords_dim`

### A1 — `image_scores` fact table

- Decompose `images.score_*` + `scores_json` into `(image_id, metric_code, value, …)` with expand-contract and view compatibility (high query churn on [modules/db.py](../../../modules/db.py))

### A2 — `job_scopes` etc.

- Normalize `jobs.scope_paths` / structured `queue_payload`

### A3 — Integrity

- CHECK constraints; `image_xmp.stack_id` vs `stacks.id` strategy per [DB_SCHEMA_REFACTOR_PLAN.md](DB_SCHEMA_REFACTOR_PLAN.md)

### Explicit non-goals (unchanged)

- `folders.phase_agg_*`, `stack_cache`, `file_name` / `file_type` — keep as caches or convenience denormalization unless there is a separate product reason to change them.

```mermaid
flowchart TD
  V0[vec_design_registry]
  V1[vec_schema_migrate]
  V2[vec_api_callers]
  V0 --> V1
  V1 --> V2
  N0[optional_Phase4_keywords]
  N1[optional_image_scores]
  V2 -.-> N0
```
