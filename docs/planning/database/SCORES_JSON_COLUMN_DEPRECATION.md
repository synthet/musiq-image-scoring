---
name: images.scores_json column deprecation
description: Timeline for retiring the legacy scoring result blob on images in favor of normalized stores
status: active
---

# Deprecate `images.scores_json` (Postgres)

## Current state

| Storage | Role |
|---------|------|
| `image_model_scores` | **Canonical** per-model raw/normalized scores, status, shadow flag |
| `image_technical_failures` | **Canonical** technical failure detection metrics |
| `images.score_general` / `score_technical` / `score_aesthetic`, `rating`, `label` | **Canonical** aggregates and user-facing metadata |
| `images.scores_json` | **Legacy** full JSON dump of the scoring engine result (`json.dumps(result)`) |

Gallery Electron no longer reads `scores_json`. REST image detail still returns the column when populated, plus `model_scores` from `image_model_scores`.

## Timeline

### Phase 1 — Stop dual-write (config)

```json
"database": {
  "write_legacy_scores_json_column": false
}
```

Default remains `true` until operators confirm `image_model_scores` and aggregate columns cover their workflows. When `false`, new scores leave `scores_json` NULL; historical rows keep their blob.

Helper: `_write_legacy_scores_json_column()` in `modules/db_legacy.py`.

Audit:

```bash
python scripts/maintenance/verify_scores_json_parity.py
python scripts/maintenance/verify_scores_json_parity.py --backfill
```

MCP `get_database_stats` includes `scores_json_parity` on Postgres when available.

### Phase 2 — Table-only reads

- Gradio gallery uses `image_model_scores` for per-model scores; legacy blob used only for inference timing display when present.
- Export paths may still include `scores_json` for raw dumps until Phase 4.
- Optional (future): persist LLM `subscores` and inference timing in `image_model_scores` or a dedicated artifacts table.

### Phase 3 — Operator signals

- Parity script: [`scripts/maintenance/verify_scores_json_parity.py`](../../../scripts/maintenance/verify_scores_json_parity.py) — rows with non-null `scores_json` but missing production `image_model_scores` (`column_only`).
- `db.get_scores_json_parity_report()` / MCP `get_database_stats` → `scores_json_parity`.
- `db.backfill_image_model_scores_from_scores_json()` parses blob `models` block into IMS.

### Phase 4 — DDL drop (Alembic 0030) — shipped

Revision `0030_drop_images_scores_json.py`:

1. Run parity audit / backfill (`column_only` blobs without a `models` block are non-scoring metadata only).
2. `DROP COLUMN images.scores_json` on Postgres.

Greenfield DDL in `modules/db_postgres.py` no longer creates the column. Code gates reads/writes via `_postgres_images_has_scores_json_column()`.

## Firebird

Out of scope for column removal: Firebird keeps `scores_json` BLOB until the engine is decommissioned. Stop-write config applies on Postgres only (Firebird always dual-writes the blob when scoring).

## References

- [API_CONTRACT.md](../../technical/API_CONTRACT.md) — `model_scores`, legacy `scores_json_parsed`
- [MODELS_SUMMARY.md](../../technical/MODELS_SUMMARY.md)
- Migration `0016_image_model_scores.py`
- [IMAGE_EMBEDDING_COLUMN_DEPRECATION.md](IMAGE_EMBEDDING_COLUMN_DEPRECATION.md) — parallel expand-contract pattern
