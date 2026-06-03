# Database Schema

PostgreSQL + pgvector is the primary database schema for Vexlum Scoring. Older Firebird schema descriptions are historical/migration context only unless current code and docs explicitly say otherwise.

## Canonical Sources

| Source | Role |
|---|---|
| [modules/db_postgres.py](../../modules/db_postgres.py) | Greenfield PostgreSQL DDL used by runtime initialization. |
| [migrations/versions/](../../migrations/versions/) | Alembic revisions for existing databases. |
| [migrations/env.py](../../migrations/env.py) | Alembic connection setup using backend PostgreSQL config. |
| [technical/API_CONTRACT.md](API_CONTRACT.md) | API-level semantics for image identity, filters, and response fields. |
| MCP `get_db_schema` | Live schema inspection when a database is reachable. |

Do not add columns or table names to docs from memory. Confirm in the sources above.

## Primary Tables

The current PostgreSQL initializer creates or maintains these application tables. This is a routing catalog, not a full column reference.

| Area | Tables |
|---|---|
| Library and folders | `folders`, `images`, `file_paths`, `deleted_images`, `pipeline_tool_folder_last_touch` |
| Runs, jobs, and execution trail | `jobs`, `job_phases`, `job_steps`, `job_image_actions`, `pipeline_phases`, `image_phase_status`, `image_incidents` |
| Metadata | `image_exif`, `image_xmp`, image identity fields on `images` |
| Scoring | composite scores on `images` (`score_general`, `score_technical`, `score_aesthetic`); per-model scores in `image_model_scores` |
| Culling and stacks | `stacks`, `stack_cache`, `cluster_progress`, `culling_sessions`, `culling_picks` |
| Keywords | `keywords_dim`, `image_keywords`, legacy keyword text fields where retained for compatibility |
| Embeddings | `embedding_spaces`, `image_embeddings`, `image_embeddings_512`, `image_embeddings_768` (legacy `images.image_embedding` dropped in migration 0024) |

## PostgreSQL / pgvector Notes

- The initializer and migrations create `CREATE EXTENSION IF NOT EXISTS vector`.
- `image_embeddings` stores 1280-dimensional vectors for the default MobileNet space.
- `image_embeddings_512` and `image_embeddings_768` store additional registered spaces.
- HNSW cosine indexes are used for vector search where supported.
- See [EMBEDDINGS.md](../EMBEDDINGS.md) and [technical/EMBEDDINGS.md](EMBEDDINGS.md) for registered space codes, producers, and dimensions.

## Migration Notes

- Alembic revisions live under [migrations/versions/](../../migrations/versions/).
- The initial schema starts at `0001_initial_schema.py`; subsequent revisions add normalized keywords, embeddings, hash/version identity, job execution trails, incidents, GPS/geocode fields, status constraints, model-score rows, pick status, and job status checks.
- Runtime greenfield DDL in [modules/db_postgres.py](../../modules/db_postgres.py) should stay aligned with Alembic-created objects.

## Historical Firebird Context

Firebird was the original database and remains documented for migration history and legacy compatibility analysis. Treat Firebird-specific docs as archived or historical unless active support is proven in current code:

- [planning/database/FIREBIRD_POSTGRES_MIGRATION.md](../planning/database/FIREBIRD_POSTGRES_MIGRATION.md)
- [technical/FIREBIRD_WINDOWS_TEMPDIR.md](FIREBIRD_WINDOWS_TEMPDIR.md)
- [archive/plans/database/INDEX.md](../archive/plans/database/INDEX.md)

## Related

- [DATABASE.md](../DATABASE.md)
- [technical/AGENT_COORDINATION.md](AGENT_COORDINATION.md)
- [image-scoring-gallery database design](https://github.com/synthet/image-scoring-gallery/blob/main/docs/architecture/02-database-design.md)
