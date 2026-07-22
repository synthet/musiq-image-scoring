---
name: backlog-queue
description: Cross-repo GitHub Project board is the canonical task queue. Use whenever picking work, claiming an issue, transitioning Stage, or filing/closing a backlog issue across image-scoring-backend or image-scoring-gallery.
---

# Backlog queue (compiled claim/stage)

> The canonical task queue is the GitHub Project board:
> **https://github.com/users/synthet/projects/1**
>
> It spans both repos: `synthet/image-scoring-backend` and `synthet/image-scoring-gallery`.
> The repo `TODO.md` files are pointers only — **never** add tasks there.

## Compiled bootloader (claim / Stage)

Do **not** hand-roll `gh project item-edit` or rediscover Stage option IDs.

```powershell
python scripts/agent_skills/backlog_stage.py claim <N>
python scripts/agent_skills/backlog_stage.py claim <N> --repo gallery
python scripts/agent_skills/backlog_stage.py set-stage <N> --stage in_progress
python scripts/agent_skills/backlog_stage.py set-stage <N> --stage blocked --comment "Blocked: …"
python scripts/agent_skills/backlog_stage.py set-stage <N> --stage review
python scripts/agent_skills/backlog_stage.py set-stage <N> --stage done
```

Slash command `/task-claim <N>` uses the same harness.

| Owner | Responsibility |
|-------|----------------|
| **Code** | Assign, project item lookup, Stage transitions |
| **LLM** | Pick highest-priority Ready card; Blocked comment prose |
| **Human** | Promote Backlog→Ready; close dead issues |

## When to use

- User asks to pick the next task, start work, or "what's next".
- Filing a new backlog item; PR needs `Closes #N`.
- Blocked / Review / Done Stage transitions.
- Agent would start work without an issue — stop and file one first.

## The five-step contract

1. **Pick** from `Stage = Ready`, sort `priority:p0..p3` (LLM judgment). Do not invent work if Ready is empty.
2. **Claim** via harness / `/task-claim` (code).
3. **In Progress** on first commit via `set-stage … --stage in_progress`.
4. **Blocked** → `set-stage … --stage blocked --comment "…"` (LLM writes comment).
5. **PR** must include `Closes #<N>`; move to `review` when opening; `done` after merge if needed.

## Filing a new task

1. Search both repos for duplicates.
2. Choose owning repo (or both + `cross-repo`).
3. Open issue with label taxonomy below; add to Project; default Stage=Backlog.
4. Promote to Ready only with maintainer signoff.

## Label taxonomy

| Family | Values |
|--------|--------|
| `area:*` | `python`, `db`, `gradio`, `electron`, `docs` |
| `priority:*` | `p0`, `p1`, `p2`, `p3` |
| `type:*` | `bug`, `feature`, `refactor`, `test`, `chore`, `epic` |
| (special) | `cross-repo` |
| (status) | `obsolete` — stay open on Backlog |

Epics: `type:epic` + GitHub sub-issues (same repo). Cross-repo: paired issues + `cross-repo` label.

Obsolete: tier-1 close+`wontfix`; tier-2 open+`status:obsolete` on Backlog.

## Don'ts

- Don't add tasks to `TODO.md`.
- Don't start work without claiming.
- Don't silently abandon Claimed/In Progress — Blocked + comment.
- Don't open a PR without `Closes #N`.

## Related

- Harness: [`scripts/agent_skills/backlog_stage.py`](../../../scripts/agent_skills/backlog_stage.py)
- Batch hygiene (separate): `scripts/housekeeping_backlog.py`
- Contract: [`docs/project/00-backlog-workflow.md`](../../../docs/project/00-backlog-workflow.md)
- Compilation: [`.agent/SKILL_COMPILATION.md`](../../../.agent/SKILL_COMPILATION.md)
