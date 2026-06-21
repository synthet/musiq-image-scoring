---
name: backlog-housekeeping
description: >-
  GitHub backlog housekeeping for image-scoring-backend and image-scoring-gallery:
  sync Project board Stage, label hygiene, tier-1 closes. Use when the user runs
  /backlog-housekeeping, asks to close stale or obsolete issues, fix board drift,
  or clean up issue labels on the synthet Project #1 queue.
---

# backlog-housekeeping

Periodic **queue truthfulness** pass across both repos on [Project board #1](https://github.com/users/synthet/projects/1). Complements [backlog-queue](../backlog-queue/SKILL.md) (claim/workflow) — this skill **reconciles** drift; it does not pick new work.

## When to use

- User asks for issue housekeeping, stale/obsolete cleanup, or board sync.
- After a merge wave left cards in **Review** or issues with **no Stage**.
- Before promoting items to **Ready** — run audit first.
- Slash command: **`/backlog-housekeeping`**.

## Preconditions

- **`gh` CLI** authenticated (`gh auth status`).
- Run from **Windows** (or any shell where `gh` is on `PATH`). Do **not** rely on WSL unless `gh` is installed there.
- Repo root: **image-scoring-backend** (script lives here; touches both repos).

## Canonical workflow

### 1. Dry-run (always first)

```powershell
cd D:\Projects\image-scoring-backend
python scripts/housekeeping_backlog.py
```

Review output: stage assignments, label edits, tier-1 closes.

### 2. Apply

```powershell
python scripts/housekeeping_backlog.py --apply
```

Runs stages → labels → config closes → post-apply audit.

### 3. Read-only audit only

```powershell
python scripts/audit_backlog_issues.py
python scripts/housekeeping_backlog.py --phase audit
```

## Phases

| Phase | Flag | What it does |
|-------|------|----------------|
| **stages** | `--phase stages` | Unstaged cards → Backlog / Ready / Done; Review → Done (closed) or Backlog (open) |
| **labels** | `--phase labels` | Auto-fix missing `area:*`, drop duplicate `bug`/`enhancement` when `type:*` exists |
| **closes** | `--phase closes` | Tier-1 closes from config (skips already closed) |
| **audit** | `--phase audit` | `audit_backlog_issues.py` only |
| **all** | default | Full pass |

## Configuration

Edit **`scripts/backlog_housekeeping_config.json`** (committed, idempotent):

```json
{
  "promote_ready": {
    "synthet/image-scoring-backend": [253, 254],
    "synthet/image-scoring-gallery": [134, 135]
  },
  "tier1_closes": [
    {
      "repo": "synthet/image-scoring-backend",
      "number": 114,
      "comment": "Closing as superseded by …"
    }
  ]
}
```

- **`promote_ready`**: open issues that get **Stage = Ready** when unstaged (active sprint).
- **`tier1_closes`**: dead / superseded / mis-filed — **close + comment + Stage = Done**. See obsolete tiers in backlog-queue skill.

Remove entries from `tier1_closes` after they are closed (script skips closed issues but keeps config tidy).

## Stage rules (script)

| Issue state | Condition | Stage |
|-------------|-----------|-------|
| CLOSED | on board, unstaged | **Done** |
| OPEN | in `promote_ready` | **Ready** |
| OPEN | otherwise | **Backlog** |
| OPEN | card stuck in **Review** | **Backlog** |
| CLOSED | card stuck in **Review** | **Done** |

## Obsolete policy (do not auto-close)

| Tier | Action |
|------|--------|
| **1 — dead** | Add to `tier1_closes` → close + `wontfix` optional + Done |
| **2 — superseded / icebox** | Keep **open** + `status:obsolete` + Backlog — **do not** close via this script |

Bulk inventory (epics, obsolete markers): `scripts/apply_backlog_inventory.py` (separate, rare).

## Report to the user

After `--apply`, summarize:

- Counts: unstaged synced, Review reconciled, labels touched, issues closed.
- Board snapshot: Backlog / Ready / Done / unstaged (expect **0** unstaged).
- Audit gaps remaining (if any): missing labels, open `status:obsolete` list.
- Config edits needed (e.g. new `promote_ready` set, new tier-1 candidate).

## Related

- [backlog-queue](../backlog-queue/SKILL.md) — claim, Stage transitions, filing issues.
- [docs/project/00-backlog-workflow.md](../../../docs/project/00-backlog-workflow.md)
- [docs/project/backlog-inventory-2026-05.md](../../../docs/project/backlog-inventory-2026-05.md)
- `scripts/audit_backlog_issues.py`, `scripts/apply_backlog_inventory.py`

## Keep in sync

Cursor slash **`.cursor/commands/backlog-housekeeping.md`** and Claude **`.claude/commands/backlog-housekeeping.md`**. Mirror this file to **`.claude/skills/backlog-housekeeping/SKILL.md`**.
