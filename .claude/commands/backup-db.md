> **Claude Code:** Same intent as Cursor `/backup-db`. When customizing, keep in sync with `.cursor/commands/backup-db.md`.

# /backup-db — PostgreSQL backup

Use when the operator wants a **local dump** of the `image_scoring` PostgreSQL database (custom-format `pg_dump`).

## Preconditions

- **Postgres reachable** at `database.postgres` from merged config (`config.json` + optional `environment.json` via `modules.config.load_config`).
- **Windows:** PowerShell available; script resolves `pg_dump` (PATH / pgAdmin) or uses **Docker** (`image-scoring-postgres` running) if no local binary.

## Action (agent)

1. From **this repo root** (`image-scoring-backend`), run **with Dropbox mirror and 7-day mirror rotation** (see skill **`.cursor/skills/backup-db/SKILL.md`**):

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Backup-Postgres.ps1 `
     -MirrorDir "D:\Dropbox\Photos\Scoring" `
     -MirrorRetentionDays 7
   ```

2. Optional parameters (only if the user asked):

   - `-BackupDir <path>` — override output folder (default: `backups\postgres` under repo root).
   - `-RetentionDays <n>` — prune **primary** folder only (`0` skips); default **30**.
   - `-MirrorDir` / `-MirrorRetentionDays` — omit mirror step or change mirror retention (defaults when mirror omitted: no copy).
   - `-ConfigPath <path>` — non-default `config.json`.

3. **Report** the primary dump path, mirror path (when used), file sizes, prune summary, and any errors. Do not claim success without a non-empty `.dump` on disk (primary and mirror when mirroring).

## Fallback (no Windows / no PowerShell)

If the script cannot run, use the same connection values as config and either:

- `pg_dump` on the host against `host:port` from config, **custom format** to a file; or  
- With Docker: `pg_dump` inside `image-scoring-postgres` to `/tmp/…`, then `docker cp` to the host (see `scripts/powershell/Backup-Postgres.ps1` for the pattern).

## After restore note

If restoring into a DB that already has data, operators may need `scripts/python/postgres_sequence_repair.py` (see repo docs / CHANGELOG).

## Done when

- A timestamped `image_scoring_*.dump` exists under the chosen backup directory, the run exited successfully, and when using the default workflow above the same filename exists under `D:\Dropbox\Photos\Scoring`.
