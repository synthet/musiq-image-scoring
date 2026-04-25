# Embedding Features: Next Steps Roadmap

This document summarizes the current implementation status and the **true remaining gaps** for the 8 proposed embedding applications.

## Status Overview

| App | Feature | Status | Implementation Notes |
|:---|:---|:---|:---|
| 01 | Diversity Selection | **Implemented** | `diversity.py` (MMR) integrated in `selection.py`. |
| 02 | Near-Duplicate Detection | **Implemented** | `similar_search.py` (`find_near_duplicates`). |
| 03 | Tag Propagation | **Implemented** | `tagging.py` (`propagate_tags`). |
| 04 | Outlier Detection | **Implemented** | `similar_search.py` (`find_outliers`). |
| 05 | 2D Embedding Map | **Backend v1 Implemented / Multi-space + UI roadmapped** | Projection service exists in `modules/projections.py`; API exposed at `GET /api/embedding_map`; coverage in `tests/test_api_embedding_map.py`. v1 covers the default 1280-d MobileNet space only. Multi-space (CLIP-512 / BLIP-768), optional PCA pre-step, HDBSCAN clustering, persistent projections table, and the React atlas UI are phased follow-ups — see [EMBEDDING_APP_05_2D_EMBEDDING_MAP.md](EMBEDDING_APP_05_2D_EMBEDDING_MAP.md) §Roadmap. |
| 06 | Smart Stack Representative | **Implemented** | Centroid representative selection is implemented in `modules/clustering.py` (`_select_best_image`, `stack_representative_strategy`). |
| 07 | "More Like This" UI | **Partial** | Search logic and REST API exist; UI wiring is still needed. |
| 08 | Gradio Integration | **Partial** | Backend APIs exist, but bidirectional control and orchestration work remain. |

---

## Implementation Verification References

Use these code references as the source of truth when reviewing status:
- `modules/projections.py` (2D projection compute + cache layer)
- `modules/api.py` (`/api/embedding_map` route)
- `tests/test_api_embedding_map.py` (API behavior and fallback/cache tests)
- `modules/clustering.py` (`_select_best_image` centroid strategy)

Similarity REST routes (search, duplicates, outliers) are listed in the root [TODO.md](../../../TODO.md); request/response shapes are described in [API_CONTRACT.md](../../technical/API_CONTRACT.md).

---

## Remaining Work (True Gaps Only)

### 1) Embedding-map multi-space (App 05, phase 1 — low risk, no schema)
- Add `embedding_space` + optional `pca_dim` parameters to `compute_embedding_map` and `GET /api/embedding_map`; bake both into the disk-cache key.
- New helper `modules/projections_db.get_embeddings_with_metadata_for_space(space_code, …)` reading from `image_embeddings_512` / `_768` via `_pg_embedding_table_for_dim`.
- Add `embedding_space` to `GET /api/similarity/search` (REST parity with the MCP tool).
- New `GET /api/images/{id}/similar` k-NN endpoint (do **not** use `/{id}/neighbors` — taken by prev/next nav).
- Tests extend `tests/test_api_embedding_map.py` with `space_code=clip_vit_b32_image` and PCA shape/determinism cases. No new dependencies.

### 2) Persistent projections + HDBSCAN (App 05, phase 2 — opt-in)
- Alembic `0013` introduces `image_embedding_projections (image_id, embedding_space_id, projection_method, projection_version, x, y, z, cluster_id, updated_at)` with a deterministic `projection_version` hash. Mirror DDL in `db_postgres._init_db_transaction()`.
- Add `hdbscan` dependency; verify install in `~/.venvs/tf`. Cluster over PCA-50, not 2D.
- New `modules/projection_runner.py` one-shot job (not a phase) wired through `job_dispatcher` with memory ceiling and resume-safe state.
- Endpoint reads from the table when `(space_code, method, version)` matches; writes back when `?persist=true`.

### 3) Electron / Gradio UX Wiring (App 05/07, phase 3)
- Connect existing similarity and embedding-map APIs to production UI flows.
- React atlas (Deck.gl ScatterplotLayer ≥10k points; Plotly fallback below) with color-by selector, side-panel k-NN, and cluster filters.
- Small new `GET /api/embedding_spaces` endpoint surfacing the registry rows for the space dropdown.
- Add user-facing interactions for map exploration and "more like this" actions.
- Keep frontend contracts aligned with backend payloads.

### 4) Bidirectional Control Channel (App 08)
- Implement or finalize a robust bi-directional channel so Electron/Gradio can trigger embedding operations and receive live progress/events.

### 5) Headless Orchestration (App 08)
- Complete headless orchestration path for embedding-driven workflows (job triggering, status tracking, and event relay) so UI and automation use the same control surface.

---

## Notes

- App 05 no longer needs to be treated as backend-planned: backend compute + endpoint + tests are in place.
- App 06 centroid representative logic is implemented and should be tracked as complete on backend.
- For App 06, `centroid` and `balanced` strategies use embeddings only when `_select_best_image` receives them (visual stack clustering); burst stack creation currently passes scores only, so those paths fall back to `score` until embeddings are supplied there.
