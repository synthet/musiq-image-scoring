# Embeddings and similarity

**Purpose:** Store **vector embeddings** (pgvector) per image/space and expose **similarity search**, duplicate/outlier helpers, and 2D map payloads for the operator UI.

**User-visible behavior:** “Find similar” flows, duplicate detection, outlier highlighting, embedding map visualization when enabled in UI.

**Primary code paths:** `modules/similar_search.py`, `modules/embedding_spaces.py`, DB embedding columns and queries in `modules/db_postgres.py` (and facade in `modules/db.py`).

**Main HTTP API (prefix `/api`):**

- `GET /similarity/search` — primary similar-image search (query params: `image_id`, `limit`, …)
- `POST /similarity/duplicates`, `GET /similarity/duplicates` — near-duplicate pairs (POST body vs GET query)
- `GET /similarity/outliers` — folder-scoped outlier detection
- Deprecated aliases: `POST /duplicates/find`, `GET /similarity/similar`, `GET /outliers` (see OpenAPI `deprecated` flags)
- `GET /embedding_map` — 2D UMAP/t-SNE projection payload for the UI (optional `space_code`, cache via query params)

**Related docs:** [EMBEDDINGS](../../technical/EMBEDDINGS.md) · [EMBEDDINGS.md](../../EMBEDDINGS.md) (hub) · planned UI specs: [features/planned/embeddings/](../planned/embeddings/README.md) (cross-link only where shipped behavior overlaps)
