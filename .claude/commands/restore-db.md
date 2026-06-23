> **Claude Code:** Same intent as Cursor `/restore-db`. When customizing, keep in sync with `.cursor/commands/restore-db.md`.

# /restore-db — PostgreSQL restore (safe)

Use when the operator wants to **restore** a custom-format `pg_dump` into the
`image_scoring` PostgreSQL database. This is the **only sanctioned restore path** —
do **not** hand-run `pg_restore` directly. An ad-hoc restore of the wrong/older dump
caused the 2026-06 data regression (an old dump rewound the live DB; `images_id_seq`
went **198499 → 190180**). `scripts/powershell/Restore-Postgres.ps1` makes that
mistake recoverable and visible.

## What the wrapper guarantees

1. **Pre-restore safety dump first** — always `pg_dump`s the *current* target DB to
   `backups\postgres\<db>_<ts>_pre-restore.dump` before touching anything. One-step rollback.
2. **Shows the source** — dump mtime/size + `pg_restore --list` header, and a BEFORE
   snapshot (`images` count + `max(id)`).
3. **Gated destructive step** — `pg_restore --clean` runs behind PowerShell
   `ShouldProcess`: `-WhatIf` previews, default prompts, `-Confirm:$false` runs unattended.
4. **Sequence repair + row-drop guard** — runs `postgres_sequence_repair.py`, prints a
   before/after diff, and **warns loudly** if the row count or `max(id)` went *down*
   (the regression signature).

## Preconditions

- **Docker** on PATH and the target container running (`image-scoring-postgres`, or
  `image-scoring-postgres-e2e` for the test instance).
- Connection (user/password/port/dbname) comes from merged config
  (`config.json` + optional `environment.json` via `modules.config.load_config`).

## Action (agent)

1. **Preview first** (no changes):

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Restore-Postgres.ps1 `
     -DumpFile .\backups\postgres\<chosen>.dump -WhatIf
   ```

2. **Restore for real** (unattended needs `-Confirm:$false`):

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\powershell\Restore-Postgres.ps1 `
     -DumpFile .\backups\postgres\<chosen>.dump -Confirm:$false
   ```

3. Optional parameters:

   - `-TargetDb <name>` — DB to restore into (default: config `dbname`).
   - `-Container <name>` — target container (default: `image-scoring-postgres`).
   - `-PgPort <n>` — HOST-mapped port for the sequence-repair step (live `5432`, e2e `5433`).
   - `-SafetyBackupDir <path>` — where the pre-restore dump is written (default `backups\postgres`).
   - `-SkipSequenceRepair` — skip sequence realignment (not recommended).

4. **Report** the safety-dump path, BEFORE/AFTER `images` count + `max(id)`, and any
   row-drop / `max(id)`-backwards warnings. Treat an unreadable `images` table after
   restore as **failure** — roll back from the safety dump.

## Choosing the right dump

Newest-by-content, not newest-by-filename. Compare candidate dumps' `images` count /
`max(id)` (the wrapper prints BEFORE; restore into the **e2e** container first to inspect
a candidate without risking live). The good rotating dumps live in `backups\postgres\`
(mirrored to `D:\Dropbox\Photos\Scoring`). Quarantined months-old dumps are under
`backups\archive\` and should not be restored unless explicitly intended.

## Recover from a bad restore

Every run prints the exact rollback command using its safety dump, e.g.:

```powershell
.\scripts\powershell\Restore-Postgres.ps1 -DumpFile "<...>_pre-restore.dump" -Confirm:$false
```

## Done when

- The intended dump is restored, sequences are repaired, the AFTER snapshot matches
  expectations (no unexpected row drop / `max(id)` regression), and the pre-restore
  safety dump exists on disk.

## Keep in sync

Cursor command **`.cursor/commands/restore-db.md`** and this file should match.
Companion: **`/backup-db`** (`.claude/commands/backup-db.md`).
