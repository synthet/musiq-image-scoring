---
name: backup-db
description: >-
  PostgreSQL custom-format backup for image-scoring-backend via Backup-Postgres.ps1. Use when the user runs /backup-db, asks for a local pg_dump, database backup, or Postgres dump. Default workflow keeps at most 3 dumps in backups/postgres and mirrors the latest copy to D:\Dropbox\Photos\Scoring (also capped at 3 files).
---

# backup-db

## Role

Run **`scripts/powershell/Backup-Postgres.ps1`** from **repo root** so the dump uses merged config (`config.json` + `environment.json` via Python when available). Report primary dump path, mirror path (if used), sizes, exit code, and prune counts.

## Canonical invocation (this operator)

Always pass **mirror** arguments and **count-based retention** so both locations keep at most **3** newest `image_scoring_*.dump` files:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Backup-Postgres.ps1 `
  -MaxBackups 3 `
  -MirrorDir "D:\Dropbox\Photos\Scoring" `
  -MirrorMaxBackups 3 `
  -RetentionDays 0 `
  -MirrorRetentionDays 0
```

- **Primary directory:** `backups\postgres` under repo root (default).
- **Mirror directory:** `D:\Dropbox\Photos\Scoring` — created if missing.
- **Rotation:** after each successful dump, oldest files beyond the third newest are deleted in each folder (newest kept by `LastWriteTime`).

## Without mirror

If the user explicitly wants **no** Dropbox copy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Backup-Postgres.ps1 `
  -MaxBackups 3 `
  -RetentionDays 0
```

## Other script parameters

- `-BackupDir <path>` — primary dump folder (default: `backups\postgres` under repo root).
- `-MaxBackups <n>` — keep newest *n* dumps in primary folder; `0` skips count prune.
- `-RetentionDays <n>` — age-based prune in primary folder (used only when `-MaxBackups 0`); `0` skips.
- `-MirrorMaxBackups <n>` — keep newest *n* mirror dumps; `0` skips count prune.
- `-MirrorRetentionDays <n>` — age-based mirror prune (used only when `-MirrorMaxBackups 0`); `0` skips.
- `-ConfigPath <path>` — non-default `config.json`.

## Success criteria

- Process exits **0**.
- Primary `.dump` exists and is **non-empty**.
- When mirroring: mirror `.dump` exists, non-empty, and prune step completed without fatal errors.
- After prune: at most **3** `image_scoring_*.dump` files in each retention-enabled folder.

## After restore

Restoring into a DB that already has data may require `scripts/python/postgres_sequence_repair.py` (see repo docs / CHANGELOG).

## Keep in sync

Cursor slash command **`.cursor/commands/backup-db.md`** and Claude **`.claude/commands/backup-db.md`** should match this workflow.
