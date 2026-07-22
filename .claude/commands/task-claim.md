> **Cursor:** Same intent as Claude `/task-claim`. When customizing, keep in sync with `.claude/commands/task-claim.md`.

# /task-claim — claim a board issue and move it to Stage=Claimed

Use when starting work on a backlog item. Hand-off in `$ARGUMENTS` is the issue number (and optional repo).

**Usage:**
```
/task-claim <issue-number> [--repo backend|gallery]
```

If `--repo` is omitted, default to `backend` (this repo).

## Compiled bootloader (do this first)

```powershell
python scripts/agent_skills/backlog_stage.py claim <N>
python scripts/agent_skills/backlog_stage.py claim <N> --repo gallery
```

Do **not** re-type project/Stage IDs or hand-roll `gh project item-list` — the harness owns them.

Later Stage flips:

```powershell
python scripts/agent_skills/backlog_stage.py set-stage <N> --stage in_progress
python scripts/agent_skills/backlog_stage.py set-stage <N> --stage blocked --comment "Blocked: <reason + unblock>"
python scripts/agent_skills/backlog_stage.py set-stage <N> --stage review
python scripts/agent_skills/backlog_stage.py set-stage <N> --stage done
```

## Ownership split

| Owner | Responsibility |
|-------|----------------|
| **Code** | Verify claimable, assign `@me`, resolve project item, set Stage |
| **LLM** | Choosing which Ready card; drafting Blocked comment text |
| **Human** | Promoting Backlog→Ready; closing issues |

## Confirm + remind

Harness JSON includes `url`, `title`, and a reminder to move to `In Progress` on first commit and include `Closes #<N>` in the PR.

## Reference

Full contract: [`docs/project/00-backlog-workflow.md`](../../docs/project/00-backlog-workflow.md) and skill [`.cursor/skills/backlog-queue/SKILL.md`](../skills/backlog-queue/SKILL.md).
Compilation: [`.agent/SKILL_COMPILATION.md`](../../.agent/SKILL_COMPILATION.md).
