---
description: Canonical task queue is the cross-repo GitHub Project board, not TODO.md. Forces every agent through claim → start → review → done transitions on Stage.
alwaysApply: true
---

# Backlog queue (rule)

The canonical task queue is the **GitHub Project board** spanning `image-scoring-backend` and `image-scoring-gallery`:

**→ https://github.com/users/synthet/projects/1**

`TODO.md` is a pointer only. Never add tasks to it.

## What every agent must do

1. **Pick from `Stage = Ready`** on the board, sorted by `priority:p0..p3`.
2. **Claim** via `/task-claim <N>` (preferred) or `gh` commands. Claiming assigns you and moves the card to `Stage = Claimed`.
3. **Flip `Stage = In Progress`** on the first commit.
4. **If blocked**, move to `Stage = Blocked` *and* comment with the reason + unblock condition. Do **not** silently drop a Claimed card.
5. **PR description must include `Closes #<N>`**. Move card to `Stage = Review` when PR opens; merging flips `Status = Done`.

Full contract, `gh` examples, and reference IDs: [`.cursor/skills/backlog-queue/SKILL.md`](mdc:.cursor/skills/backlog-queue/SKILL.md) and [`docs/project/00-backlog-workflow.md`](mdc:docs/project/00-backlog-workflow.md).

## Filing new tasks

Open a GitHub issue in the appropriate repo (cross-repo work → both, with `cross-repo` label). Add to the Project board. **Don't write tasks into `TODO.md`** — the file will be regenerated as a pointer and your edits will be lost.

## Don'ts

- Don't start work without an issue. Stop and file one first.
- Don't skip Stage transitions — the queue must reflect reality.
- Don't open a PR without `Closes #<N>`; the PR template enforces it.
