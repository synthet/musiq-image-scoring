# Refined Cross-Repo Migration Plan: Firebird -> PostgreSQL + pgvector

Date: 2026-03-08 (updated 2026-04-01)  
Status: **Decommissioning Complete** — Firebird infrastructure removed; system fully PostgreSQL-native.  
Scope: **image-scoring-backend** + **image-scoring-gallery** coordinated migration

## Summary

- Treat this as a **coordinated platform migration** across both repos (**image-scoring-backend** and **image-scoring-gallery**), not a frontend-only or backend-only DB split.
- Keep your selected rollout defaults: **phased dual-write**, **Postgres in local Docker**, **Python app + MCP as day-1 cutover scope**.
- Add explicit **Electron migration gates** before final Firebird retirement, aligned with Electron docs that currently recommend Firebird until coordinated migration is ready.

## Key Implementation Changes

1. **Readiness / Governance (Phase 0)**
- Freeze schema baseline from live Firebird and define versioned SQL migrations (move away from implicit startup DDL as migration mechanism).
- Lock migration invariants: preserve IDs, preserve FK behavior, preserve embedding dimension `1280`, preserve API response shapes.
- Add a migration runbook with rollback window and ownership split by repo.

2. **Postgres Foundation (Phase 1)**
- Stand up PostgreSQL + `pgvector` in Docker.
- Create full schema for active tables used by app + pipeline + phase tracking (`IMAGES`, `FILE_PATHS`, `FOLDERS`, `STACKS`, `CLUSTER_PROGRESS`, `CULLING_*`, `JOBS`, `PIPELINE_PHASES`, `IMAGE_PHASE_STATUS`, `JOB_PHASES`, `STACK_CACHE`, plus optional empty tables `IMAGE_EXIF`, `IMAGE_XMP`).
- Map `images.image_embedding` from Firebird blob to `vector(1280)`; add HNSW cosine index.

3. **Data Migration + Dual-Write (Phase 2)**
- Build resumable Firebird->Postgres backfill (chunked by PK, idempotent upserts, sequence `setval` sync).
- Enable **Python-side dual-write** (Firebird primary write, Postgres secondary write with retry queue and replay).
- Keep Firebird as read source until parity gates pass.

4. **Python + MCP Cutover (Phase 3)**
- Add backend-aware DB adapter in `modules.db` (same public function signatures).
- Switch Python reads to Postgres after parity + performance gates.
- Replace `firebird-admin` MCP with `postgres-admin`; keep old Firebird admin in read-only rollback mode during stabilization.

5. **Electron Alignment Before Final Decommission (Phase 4)**
- Add DB provider abstraction in Electron main-process DB layer (`electron/db.ts`) while preserving IPC contracts.
- Migrate Electron from `node-firebird` to Postgres client only after Python cutover stabilizes.
- Remove Firebird-specific runtime assumptions (port checks, auto-start server path, Firebird-only SQL).
- Final Firebird decommission only after Electron + Python both pass production soak on Postgres.

## Public API / Interface Changes

- **image-scoring-backend** (`config.json`) keys:
- `database.engine` (`firebird|postgres`)
- `database.filename` (used by Firebird mode)
- optional `database.dual_write` (Firebird primary write + Postgres secondary write)
- `database.postgres.{host,port,dbname,user,password}`
- Electron config:
- `database.engine` (`firebird|postgres`)
- `database.postgres.*` connection block
- MCP config:
- add `postgres-admin`, phase out `firebird-admin` after rollback window
- Keep existing REST/MCP payload contracts stable during migration.

### Migration mode config examples

Use the same key names as `modules/config.py` validation and `modules/db_postgres.py` connection loading.

```json
{
  "database": {
    "engine": "firebird",
    "filename": "scoring_history.fdb",
    "dual_write": true,
    "postgres": {
      "host": "127.0.0.1",
      "port": 5432,
      "dbname": "musiq",
      "user": "musiq",
      "password": "musiq"
    }
  }
}
```

- **Firebird only**: set `database.engine` to `firebird`; `database.filename` is required.
- **Postgres only**: set `database.engine` to `postgres`; `database.postgres.host|port|dbname|user` are required.
- **Migration/dual-write mode**: keep `engine=firebird` and set `database.dual_write=true` so Firebird remains the primary store while writes are mirrored to Postgres.

## Test Plan

1. **Data parity**
- Table counts and PK coverage parity per migrated table.
- FK integrity checks in Postgres.
- Sampled row-hash parity on high-value columns.

2. **Embedding/vector correctness**
- Non-null vector count parity.
- Dimension enforcement (`1280`) and conversion validation from Firebird blob.
- Similar search top-K overlap and score tolerance checks.

3. **Behavioral parity**
- Endpoint parity for `/similar`, duplicates, outliers, job/status flows.
- MCP tool parity between old and new admin paths.

4. **Performance + reliability**
- p95 latency targets for similarity and duplicate candidate queries.
- Dual-write retry queue drain tests and failure injection.
- Full rollback drill (toggle reads back to Firebird).

5. **Cross-repo acceptance**
- Python app + MCP pass on Postgres.
- Electron IPC workflows pass after provider switch.
- Only then allow Firebird retirement.

## Current Implementation Status (2026-03-31)

### Phase 0 — Schema baseline ✅
- Migration plan: this document
- Alembic configured: `alembic.ini` + `migrations/env.py` + `migrations/versions/0001_initial_schema.py`
- `modules/db_postgres.py` `init_db()` covers all 17 tables

### Phase 1 — Postgres Foundation ✅
- `docker-compose.yml` — Postgres + pgvector Docker stack (`pgvector/pgvector:pg17`)
- `modules/db_postgres.py` — connection pool (ThreadedConnectionPool 1–20) + full schema init (17 tables, all indexes, HNSW cosine on `image_embedding`)
- `scripts/python/migrate_firebird_to_postgres.py` — chunked, resumable bulk migration with `--dry-run` and `--batch-size` flags
- `scripts/powershell/Setup-PostgresDocker.ps1` — helper to start the container

### Phase 2 — Dual-Write ✅ (superseded)

The dual-write plumbing in `modules/db.py` (`FirebirdCursorProxy`, `_dual_write_worker`,
`init_dual_write()`, `get_dual_write_stats()`) is retained for rollback scenarios but is
**no longer active** — Phase 3 runs Postgres as the sole primary engine.

> **Status:** Infrastructure complete but superseded by Phase 3 cutover. Dual-write is auto-disabled when `engine=postgres`.

**To activate dual-write** (set `dual_write: true` in `config.json` and start Postgres Docker):

```json
"database": {
    "engine": "firebird",
    "filename": "scoring_history.FDB",
    "user": "sysdba",
    "password": "masterkey",
    "dual_write": true,
    "postgres": {
        "host": "127.0.0.1",
        "port": 5432,
        "dbname": "image_scoring",
        "user": "postgres",
        "password": "postgres"
    }
}
```

Start Postgres:

```powershell
docker compose -f docker-compose.yml up -d
```

Init the Postgres schema (one-time):

```bash
# In WSL with ~/.venvs/tf activated:
python -c "from modules.db_postgres import init_db; init_db()"
# Or via Alembic (creates tables + marks revision as current):
alembic upgrade head
```

Bulk-migrate existing Firebird data:

```bash
python scripts/python/migrate_firebird_to_postgres.py
```

Verify parity:

```bash
python scripts/python/migrate_firebird_to_postgres.py --dry-run
```

### Phase 3 — Python + MCP Cutover ✅ (Complete)

#### Transport-layer abstraction (`modules/db_connector/`) ✅

A new connector layer was added to decouple SQL execution from engine selection.
See [`docs/architecture/DB_CONNECTOR.md`](../../architecture/DB_CONNECTOR.md) for full design.

| `database.engine` | Connector | Notes |
|---|---|---|
| `"firebird"` (default) | `FirebirdConnector` | wraps `db.get_db()`; dual-write passthrough |
| `"postgres"` | `PostgresConnector` | wraps psycopg2 pool; auto-translates via `_translate_fb_to_pg()` |
| `"api"` | `ApiConnector` | HTTP proxy to `/api/db/query`; for remote workers |

~128 public functions in `db.py` now use `get_connector()` for all database access.
The remaining 8 functions use legacy `get_db()` / `connection()` paths:

| Function | Reason for legacy path |
|---|---|
| `execute_readonly_sql_for_api` | SQL bridge — receives raw SQL from Electron IPC; engine-aware by design |
| `execute_write_sql_for_api` | SQL bridge — same |
| `validate_readonly_sql_for_api` | Validation helper — no DB access |
| `validate_write_sql_for_api` | Validation helper — no DB access |
| `init_db` | Bootstrap — must be engine-aware |
| `reset_init_db_state_for_tests` | Test infrastructure |
| `update_job_status` | Uses `connection()` context manager (routes correctly; connector migration deferred) |
| `set_image_phase_status` | Uses `connection()` context manager (routes correctly; connector migration deferred) |

#### Read/write routing via `_get_db_engine()` (~60 functions)

Setting `"engine": "postgres"` in `config.json` routes the following to PostgreSQL:

| Function | Module |
|---|---|
| `find_image_id_by_path` | `db.py` |
| `find_image_id_by_uuid` | `db.py` |
| `get_all_folders` | `db.py` |
| `get_job` | `db.py` |
| `get_image_phase_statuses` | `db.py` |
| `get_all_phases` | `db.py` |
| `get_embeddings_for_search` | `db.py` |
| `get_embeddings_with_metadata` | `db.py` |
| `get_image_count` | `db.py` |
| `get_images_paginated_with_count` | `db.py` |
| `get_all_paths` | `db.py` |
| `get_resolved_path` | `db.py` |
| `get_image_details` | `db.py` |
| `get_image_by_hash` | `db.py` |
| `get_job_phases` | `db.py` |
| `get_jobs` | `db.py` |
| `get_all_images` | `db.py` |
| `get_incomplete_records` | `db.py` |
| `get_queued_jobs` | `db.py` (uses `STRING_AGG` instead of Firebird `LIST()`) |
| `get_folder_by_id` | `db.py` |
| `get_image_exif` | `db.py` |
| `get_image_xmp` | `db.py` |
| `get_culling_session` | `db.py` |
| `get_active_culling_sessions` | `db.py` |
| `get_session_picks` | `db.py` |
| `get_session_groups` | `db.py` |
| `get_images_in_stack` | `db.py` |
| `get_stack_count` | `db.py` |
| `get_clustered_folders` | `db.py` |
| `get_phase_id` | `db.py` |
| `get_images_by_folder` | `db.py` |
| `get_nef_paths_for_research` | `db.py` |
| `get_image_ids_by_paths` | `db.py` |

#### SQL translation (`_translate_fb_to_pg()`)

Rules implemented in `modules/db.py` (line ~231):
- `UPDATE OR INSERT … MATCHING` → `INSERT … ON CONFLICT DO UPDATE`
- `SELECT FIRST n` / `FETCH FIRST n ROWS ONLY` → `LIMIT n`
- `DATEDIFF(UNIT FROM a TO b)` → `EXTRACT(…)` ⚠️ **BUG — see below**
- `?` → `%s` (outside string literals)
- `RAND()` → `RANDOM()`, `LIST(col, sep)` → `STRING_AGG(col, sep)`
- `substr()` → `substring()`, `length()` → `char_length()`

#### PostgreSQL schema additions
- `keywords_dim` and `image_keywords` tables added to `db_postgres.init_db()`
- `execute_write()` and `execute_write_returning()` helpers in `db_postgres.py`

#### Known bugs (Resolved)

**BUG 1 — DATEDIFF division operator** fixed in prior commits.
**BUG 2 — proxy translation** design verified as not a bug.

**Phase 3 is now active:** `engine` is set to `postgres` in `config.json`.
All `_get_db_engine()` routing branches have been eliminated — no function in `db.py` directly
checks engine type anymore (except the 2 SQL bridge functions that receive raw Firebird SQL
from Electron clients and translate on the fly).

### Phase 4 — Electron Alignment ✅ (Complete)

Completed 2026-03-30:
- `electron/db/provider.ts` provides a connector abstraction (`PostgresConnector`, `ApiConnector`)
- `node-firebird` dependency removed; `pg` (node-postgres) is the production driver
- Legacy `engine: "firebird"` config values automatically map to the Postgres connector
- All Firebird-specific runtime assumptions removed (port checks, auto-start server, Firebird SQL syntax)
- Firebird MCP server entry removed from `.cursor/mcp.json`

### Phase 5 — Cleanup & Decommissioning ✅ (Complete)

Completed 2026-04-01:
- **Binary Cleanup**: Deleted `SCORING_HISTORY.FDB`, `SCORING_HISTORY_TEST.FDB`, and `template.fdb` (~1.4GB disk space reclaimed).
- **Client Removal**: Deleted bundled `Firebird/` (Windows) and `FirebirdLinux/` client libraries.
- **Script Archiving**: Moved `migrate_to_firebird.py`, `check_firebird.py`, and `reset_firebird_sequences.py` to `scripts/archive_firebird/`.
- **Logic Decommissioning**: 
    - Removed `FirebirdCursorProxy` and dual-write worker/queue from `modules/db.py`.
    - Removed `FirebirdConnector` implementation; updated factory to map legacy `firebird` engine to `PostgresConnector` with a deprecation warning.
    - Cleaned `modules/mcp_server.py` of Firebird driver imports and non-standard SQL keywords (e.g., `STARTING WITH`).
- **Config Cleanup**: Removed legacy Firebird keys from `config.json` and `mcp_config.json`.

---

## Remaining Debt

### SQL Translation Layer
The `_translate_fb_to_pg()` function in `modules/db.py` remains active. It allows the PostgreSQL-native system to support legacy Firebird-dialect SQL while running on PostgreSQL. 
- **Risk**: Low (Stable and tested).
- **Benefit**: Maintains compatibility with Electron IPC calls without requiring a massive coordinated SQL rewrite.
- **Future**: Should be removed once all ~60 DB-interacting functions are audited and converted to native PostgreSQL syntax (`%s` placeholders, standard SQL functions).

---

## Assumptions and Defaults

- The exact file path you gave ([migration-plan.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/technical/migrations/firebird-to-postgresql-pgvector-migration-plan.md)) was not found locally; refinement is based on nearby Electron docs:
- `docs/technical/architecture/DATABASE.md`
- `docs/technical/architecture/OVERVIEW.md`
- Day-1 cutover remains Python + MCP; Electron migration is required before final decommission.
- Deployment default remains local Docker Postgres for initial rollout.
