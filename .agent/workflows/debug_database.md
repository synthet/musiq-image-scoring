---
description: Debug database connectivity and schema — PostgreSQL + pgvector
---

## Purpose

Isolate **database** problems: connectivity, extension (`pgvector`), migrations, read-only consistency checks.

## When to use

- Doctor reports DB FAIL; migrations needed; ORM/query errors; MCP `check_database_health` flags issues.

## Canonical docs first

- [docs/DATABASE.md](../../docs/DATABASE.md)
- [docs/DIAGNOSTICS.md](../../docs/DIAGNOSTICS.md)
- [docs/technical/DB_SCHEMA.md](../../docs/technical/DB_SCHEMA.md)
- [docs/CANONICAL_SOURCES.md](../../docs/CANONICAL_SOURCES.md)

## Safe commands

```bash
source ~/.venvs/tf/bin/activate
python scripts/doctor.py --no-gpu
```

- Apply migrations when intentional: `alembic upgrade head` (from repo root, correct env).
- **Read-only MCP:** `get_database_engine_info`, `check_database_health`, `execute_sql` (SELECT-only), `get_db_schema`.

## Files commonly touched (implementation phase)

- `modules/db_postgres.py`, `migrations/versions/*`, `docs/technical/DB_SCHEMA.md`

## Common failure modes

- Postgres not listening on `localhost:5432`.
- `pgvector` extension missing in the database.
- Engine set to `firebird` on a Postgres-only deployment (legacy).

## Do not

- Do not run bulk DELETE/UPDATE without backup and ticket.
- Do not use Firebird MCP tooling as default for app tables — prefer Postgres diagnostics.
