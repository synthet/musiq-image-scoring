# Database

Hub page — PostgreSQL (+ pgvector) is primary; Firebird is legacy.

## Schema and SQL

- **[technical/DB_SCHEMA.md](technical/DB_SCHEMA.md)** — tables, columns, conventions.
- **[planning/database/FIREBIRD_POSTGRES_MIGRATION.md](planning/database/FIREBIRD_POSTGRES_MIGRATION.md)** — migration status and history.

## Migrations

- Alembic revisions under **[../migrations/versions/](../migrations/versions/)** — run `alembic upgrade head` from repo root when using Postgres.

## Vectors / embeddings

- **[EMBEDDINGS.md](EMBEDDINGS.md)** — dimensions, spaces, pgvector notes (links to full technical page).

## Health

- `python scripts/doctor.py` — connectivity and **pgvector** extension check; [DIAGNOSTICS.md](DIAGNOSTICS.md).
