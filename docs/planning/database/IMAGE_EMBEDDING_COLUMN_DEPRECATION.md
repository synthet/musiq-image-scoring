---
name: images.image_embedding column deprecation
description: Timeline for retiring the legacy pgvector column on images in favor of image_embeddings
status: active
issue: https://github.com/synthet/image-scoring-backend/issues/225
---

# Deprecate `images.image_embedding` (Postgres)

## Current state

| Storage | Role |
|---------|------|
| `embedding_spaces` + `image_embeddings` | **Canonical** for 1280-d MobileNet (`mobilenet_v2_imagenet_gap`) |
| `images.image_embedding` | **Legacy** duplicate; dual-write/read during transition |
| `image_embeddings_512` / `_768` | Other spaces (never used the `images` column) |

Gallery (`image-scoring-gallery`) reads `image_embeddings` only.

## Timeline

### Phase 0 — Parity audit

```bash
python scripts/maintenance/verify_embedding_column_parity.py
python scripts/maintenance/verify_embedding_column_parity.py --backfill
```

Exit when `column_only` is 0.

### Phase 1 — Stop dual-write (config)

```json
"database": {
  "write_legacy_image_embedding_column": false
}
```

Default remains `true` until operators confirm parity. After Alembic **0024**, the column is gone and dual-write is disabled automatically.

### Phase 2 — Table-only reads

Code uses `_postgres_has_default_embedding_sql()` and `_postgres_default_embedding_select_expr()` so Postgres queries do not depend on the legacy column when it is absent or config is `false`.

### Phase 3 — Operator signals

- `verify_embedding_column_parity.py` report fields: `column_only`, `legacy_column_rows`, `legacy_column_dropped`
- MCP `get_embedding_stats` includes `legacy_column_rows` when the column still exists

### Phase 4 — DDL drop (Alembic 0024)

Revision `0024_drop_images_image_embedding.py`:

1. Final backfill into `image_embeddings`
2. `DROP INDEX idx_images_embedding_hnsw`
3. `DROP COLUMN images.image_embedding`

Greenfield DDL in `modules/db_postgres.py` no longer creates the column.

## Firebird

Out of scope: Firebird keeps `images.image_embedding` BLOB until the engine is removed.

## References

- [EMBEDDINGS.md](../../technical/EMBEDDINGS.md)
- [DB_VECTORS_REFACTOR.md](DB_VECTORS_REFACTOR.md)
- [POSTGRES_SCHEMA_OPTIMIZATIONS.md](POSTGRES_SCHEMA_OPTIMIZATIONS.md) — task A1
