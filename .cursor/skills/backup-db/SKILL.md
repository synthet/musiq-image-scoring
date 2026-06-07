---
name: backup-db
description: >-
  PostgreSQL custom-format backup for image-scoring-backend via Backup-Postgres.ps1. Use when the user runs /backup-db, asks for a local pg_dump, database backup, or Postgres dump. Default workflow keeps the repo copy under backups/postgres and mirrors a copy to D:\Dropbox\Photos\Scoring with 7-day rotation in the mirror folder only.
---

# backup-db

## Role

Run **`scripts/powershell/Backup-Postgres.ps1`** from **repo root** so the dump uses merged config (`config.json` + `environment.json` via Python when available). Report primary dump path, mirror path (if used), sizes, exit code, and prune counts.

## Canonical invocation (this operator)

Always pass **mirror** arguments so a second copy lands in Dropbox and old mirror files are removed after **one week** (repo `backups\postgres` retention stays the script default, usually 30 days):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Backup-Postgres.ps1 `
  -MirrorDir "D:\Dropbox\Photos\Scoring" `
  -MirrorRetentionDays 7
```

- **Mirror directory:** `D:\Dropbox\Photos\Scoring` — created if missing.
- **Mirror rotation:** only files matching `image_scoring_*.dump` in that folder with `LastWriteTime` older than 7 days are deleted (the new dump is copied first, then prune runs).

## Without mirror

If the user explicitly wants **no** Dropbox copy:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Backup-Postgres.ps1
```

## Other script parameters

- `-BackupDir <path>` — primary dump folder (default: `backups\postgres` under repo root).
- `-RetentionDays <n>` — prune primary folder; `0` skips.
- `-MirrorRetentionDays 0` — copy to mirror but do not delete old mirror dumps.
- `-ConfigPath <path>` — non-default `config.json`.

## Success criteria

- Process exits **0**.
- Primary `.dump` exists and is **non-empty**.
- When mirroring: mirror `.dump` exists, non-empty, and prune step completed without fatal errors.

## After restore

Restoring into a DB that already has data may require `scripts/python/postgres_sequence_repair.py` (see repo docs / CHANGELOG).

## Keep in sync

Cursor slash command **`.cursor/commands/backup-db.md`** and Claude **`.claude/commands/backup-db.md`** should match this workflow.
