> **Claude Code:** Same intent as Cursor `/backup-db`. When customizing, keep in sync with `.cursor/commands/backup-db.md`.

# /backup-db — PostgreSQL backup

Use when the operator wants a **local dump** of the `image_scoring` PostgreSQL database (custom-format `pg_dump`).

## Preconditions

- **Postgres reachable** at `database.postgres` from merged config (`config.json` + optional `environment.json` via `modules.config.load_config`).
- **Windows:** PowerShell available; script resolves `pg_dump` (PATH / pgAdmin) or uses **Docker** (`image-scoring-postgres` running) if no local binary.

## Action (agent)

1. From **this repo root** (`image-scoring-backend`), run:

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Backup-Postgres.ps1
   ```

2. Optional parameters (only if the user asked):

   - `-BackupDir <path>` — override output folder (default: `backups\postgres` under repo root).
   - `-RetentionDays 0` — skip pruning old `*.dump` files.
   - `-ConfigPath <path>` — non-default `config.json`.

3. **Report** the final dump path, file size, and any errors. Do not claim success without a non-empty `.dump` on disk.

## Fallback (no Windows / no PowerShell)

If the script cannot run, use the same connection values as config and either:

- `pg_dump` on the host against `host:port` from config, **custom format** to a file; or  
- With Docker: `pg_dump` inside `image-scoring-postgres` to `/tmp/…`, then `docker cp` to the host (see `scripts/powershell/Backup-Postgres.ps1` for the pattern).

## After restore note

If restoring into a DB that already has data, operators may need `scripts/python/postgres_sequence_repair.py` (see repo docs / CHANGELOG).

## Done when

- A timestamped `image_scoring_*.dump` exists under the chosen backup directory and the run exited successfully.
