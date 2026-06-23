> **Claude Code:** Same intent as Cursor `/backup-db`. When customizing, keep in sync with `.cursor/commands/backup-db.md`.

# /backup-db — PostgreSQL backup

Use when the operator wants a **local dump** of the `image_scoring` PostgreSQL database (custom-format `pg_dump`).

## Preconditions

- **Postgres reachable** at `database.postgres` from merged config (`config.json` + optional `environment.json` via `modules.config.load_config`).
- **Windows:** PowerShell available; script resolves `pg_dump` (PATH / pgAdmin) or uses **Docker** (`image-scoring-postgres` running) if no local binary.

## Action (agent)

1. From **this repo root** (`image-scoring-backend`), run **with Dropbox mirror and max-3 retention** (see skill **`.cursor/skills/backup-db/SKILL.md`**):

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Backup-Postgres.ps1 `
     -MaxBackups 3 `
     -MirrorDir "D:\Dropbox\Photos\Scoring" `
     -MirrorMaxBackups 3 `
     -RetentionDays 0 `
     -MirrorRetentionDays 0
   ```

2. Optional parameters (only if the user asked):

   - `-BackupDir <path>` — override output folder (default: `backups\postgres` under repo root).
   - `-MaxBackups <n>` / `-MirrorMaxBackups <n>` — change count cap (`0` skips count prune).
   - `-RetentionDays <n>` / `-MirrorRetentionDays <n>` — age-based prune when count cap is `0`.
   - `-MirrorDir` — omit mirror step when empty or not passed.
   - `-ConfigPath <path>` — non-default `config.json`.

3. **Report** the primary dump path, mirror path (when used), file sizes, prune summary, and any errors. Do not claim success without a non-empty `.dump` on disk (primary and mirror when mirroring).

## Fallback (no Windows / no PowerShell)

If the script cannot run, use the same connection values as config and either:

- `pg_dump` on the host against `host:port` from config, **custom format** to a file; or  
- With Docker: `pg_dump` inside `image-scoring-postgres` to `/tmp/…`, then `docker cp` to the host (see `scripts/powershell/Backup-Postgres.ps1` for the pattern).

## After restore note

To **restore** a dump, use the sanctioned wrapper **`/restore-db`** (`.claude/commands/restore-db.md` → `scripts/powershell/Restore-Postgres.ps1`), which takes a pre-restore safety dump, gates the destructive step, repairs sequences, and warns on row-count regressions. Do not hand-run `pg_restore` — that caused the 2026-06 data loss. The wrapper invokes `scripts/python/postgres_sequence_repair.py` for you.

## Done when

- A timestamped `image_scoring_*.dump` exists under the chosen backup directory, the run exited successfully, and when using the default workflow above the same filename exists under `D:\Dropbox\Photos\Scoring` with at most **3** dumps in each folder.
