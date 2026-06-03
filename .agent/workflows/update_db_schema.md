---
description: Update database schema — DDL, Alembic, DB_SCHEMA reference
---

## Purpose

Ship schema changes safely: migrations, reference docs, gallery coordination.

## When to use

- New columns/tables/indexes; pgvector-related DDL; data model change.

## Canonical docs first

- [docs/technical/DB_SCHEMA.md](../../docs/technical/DB_SCHEMA.md)
- [modules/db_postgres.py](../../modules/db_postgres.py)
- [migrations/versions/](../../migrations/versions/)
- [docs/CANONICAL_SOURCES.md](../../docs/CANONICAL_SOURCES.md)

## Safe order

1. Design change with backward compatibility notes.
2. Alembic migration in `migrations/versions/`.
3. Update `modules/db_postgres.py` / DAL as needed.
4. Refresh **DB_SCHEMA.md** (authoritative narrative for humans).
5. If IPC/query shapes for gallery change: [cross_repo_contract_change.md](cross_repo_contract_change.md).
6. Run targeted tests (`db` / `postgres` markers as appropriate per TESTING.md).

## Do not

- Do not rewrite committed migrations casually; add new revisions.
- Do not surprise-remove columns still referenced by gallery `electron/db.ts` without coordinated PR.
