# Database

PostgreSQL + pgvector is the primary database architecture for Vexlum Scoring. Firebird references in this repo are historical, migration, or compatibility notes unless current code and canonical docs prove an active path.

## Schema Source

- [technical/DB_SCHEMA.md](technical/DB_SCHEMA.md) - schema authority map and table catalog.
- [modules/db_postgres.py](../modules/db_postgres.py) - greenfield PostgreSQL DDL used by app initialization.
- [migrations/versions/](../migrations/versions/) - Alembic migration history for existing databases.
- [technical/API_CONTRACT.md](technical/API_CONTRACT.md) - HTTP semantics for image identity fields such as `image_hash`, `hash_version`, and `image_uuid`.

Do not invent columns from old examples. Confirm them in [technical/DB_SCHEMA.md](technical/DB_SCHEMA.md), `modules/db_postgres.py`, Alembic, or a live schema query through MCP `get_db_schema`.

## Migrations

Alembic is the versioned migration path:

```bash
alembic upgrade head
```

The greenfield initializer in [modules/db_postgres.py](../modules/db_postgres.py) should mirror migration-created tables, indexes, extensions, and seed rows. When changing schema, update both migration and initializer behavior as appropriate.

## Embeddings And Vectors

pgvector is used for visual embeddings:

- `embedding_spaces` registers vector spaces and dimensions.
- `image_embeddings` stores 1280-dimensional MobileNet vectors.
- `image_embeddings_512` and `image_embeddings_768` store additional registered spaces where enabled.
- HNSW cosine indexes support similarity search.

Read [EMBEDDINGS.md](EMBEDDINGS.md) and [technical/EMBEDDINGS.md](technical/EMBEDDINGS.md) before changing vector persistence or search behavior.

## Doctor Health Check

Use the doctor CLI before and after database or infrastructure changes:

```bash
source ~/.venvs/tf/bin/activate
python scripts/doctor.py
python scripts/doctor.py --no-gpu
python scripts/doctor.py --json
```

The doctor checks config shape, database connectivity, a query ping, pgvector availability, and optional CUDA/GPU status. Details: [DIAGNOSTICS.md](DIAGNOSTICS.md).

## Cross-Repo Consumers

The gallery consumes the backend-owned schema through PostgreSQL or backend API mode. Schema changes must follow [technical/AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md) and then update gallery code/docs:

- [image-scoring-gallery database design](https://github.com/synthet/image-scoring-gallery/blob/main/docs/architecture/02-database-design.md)
- [image-scoring-gallery canonical sources](https://github.com/synthet/image-scoring-gallery/blob/main/docs/CANONICAL_SOURCES.md)
