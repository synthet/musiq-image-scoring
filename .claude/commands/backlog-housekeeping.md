> **Cursor:** Same intent as Claude `/backlog-housekeeping`. When customizing, keep in sync with `.claude/commands/backlog-housekeeping.md`.

# /backlog-housekeeping — sync GitHub Project board and issue labels

Use when the queue has drift: unstaged cards, Review cards for merged work, missing labels, or tier-1 stale issues to close.

**Board:** https://github.com/users/synthet/projects/1 (both repos)

## Preconditions

- `gh auth status` succeeds.
- Run from **image-scoring-backend** repo root on **Windows** (or wherever `gh` is on PATH).

## Action (agent)

Read skill **`.cursor/skills/backlog-housekeeping/SKILL.md`** and follow it.

### 1. Dry-run

```powershell
cd D:\Projects\image-scoring-backend
python scripts/housekeeping_backlog.py
```

Show the user what would change (stages, labels, closes). **Stop here** if the user only asked for a preview.

### 2. Apply (when user wants changes)

```powershell
python scripts/housekeeping_backlog.py --apply
```

### 3. Optional single phase

```powershell
python scripts/housekeeping_backlog.py --apply --phase stages
python scripts/housekeeping_backlog.py --apply --phase labels
python scripts/housekeeping_backlog.py --phase audit
```

### 4. Config edits (maintainer)

Before apply, update **`scripts/backlog_housekeeping_config.json`** when:

- A new sprint should land in **Ready** → add issue numbers under `promote_ready`.
- A tier-1 dead/superseded issue should close → add to `tier1_closes` with a full comment.

Do **not** add tier-2 `status:obsolete` icebox items to `tier1_closes`.

## Report back

- Counts from script output (stages, labels, closes).
- Post-apply audit summary (missing labels should be empty).
- Board: unstaged count should be **0**.
- Any manual follow-ups (codex branch triage, new tier-1 candidates).

## Related

- `/task-claim` — start work on a Ready card.
- Skill [backlog-queue](../skills/backlog-queue/SKILL.md) — full queue contract.
- `scripts/audit_backlog_issues.py`, `scripts/apply_backlog_inventory.py` (bulk inventory, rare).

## Done when

- Dry-run reviewed (or `--apply` completed successfully).
- User has a short summary of board state and remaining audit gaps.
