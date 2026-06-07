---
name: backlog-queue
description: Cross-repo GitHub Project board is the canonical task queue. Use whenever picking work, claiming an issue, transitioning Stage, or filing/closing a backlog issue across image-scoring-backend or image-scoring-gallery.
---

# Backlog queue (Cursor canonical)

> The canonical task queue is the GitHub Project board:
> **https://github.com/users/synthet/projects/1**
>
> It spans both repos: `synthet/image-scoring-backend` and `synthet/image-scoring-gallery`.
> The repo `TODO.md` files are pointers only — **never** add tasks there.

## When to use

Trigger this skill whenever any of these are true:

- The user asks to pick the next task, start work, or "what's next".
- The user asks to file a new backlog item.
- A PR is being prepared and needs a `Closes #N` reference.
- A task has hit a blocker, is ready for review, or is finished.
- The user mentions `Stage`, `Ready`, `Backlog`, `Claimed`, `Blocked`, `Review`, or `Done` in the queue sense.
- An agent picks up a task without a corresponding issue — stop and file one first.

## The five-step contract

Every contributor (human or AI) follows the same five steps. Do **all** of them; skipping a step puts the queue out of sync.

### 1. Pick from `Stage = Ready`

Open the [Project board](https://github.com/users/synthet/projects/1), filter to **Stage = Ready**, sort by `priority:p0..p3`. Pick the highest-priority unassigned card.

If `Ready` is empty, stop and ask the maintainer to promote items from `Backlog`. **Do not invent new work.**

### 2. Claim the issue

Use the slash command:

```
/task-claim <issue-number>
```

Or run `gh` directly:

```bash
REPO="image-scoring-backend"   # or image-scoring-gallery
N=<issue-number>

# Verify claimable
gh issue view "$N" --repo "synthet/$REPO" --json number,state,assignees,title

# Assign yourself
gh issue edit "$N" --repo "synthet/$REPO" --add-assignee @me

# Find the project item and move it to Claimed
ITEM_ID=$(gh project item-list 1 --owner synthet --format json --limit 200 \
  | jq -r --argjson n "$N" --arg repo "$REPO" \
      '.items[] | select(.content.number==$n) | select((.content.repository // "") | endswith($repo)) | .id')

gh project item-edit \
  --id "$ITEM_ID" \
  --project-id PVT_kwHOAFXgIs4BWC3c \
  --field-id PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0 \
  --single-select-option-id 1cc70f0b   # Claimed
```

### 3. Flip to `In Progress` on first commit

```bash
gh project item-edit --id "$ITEM_ID" \
  --project-id PVT_kwHOAFXgIs4BWC3c \
  --field-id PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0 \
  --single-select-option-id 8b22e18e   # In Progress
```

### 4. If blocked, mark + comment

Move to `Blocked` (`4bbe5dd0`) **and** comment with the reason and unblock condition:

```bash
gh issue comment <N> --repo synthet/<repo> --body "Blocked: <one-line reason + what would unblock>."
```

### 5. PR references the issue

Your PR description **must** contain:

```
Closes #<N>
```

Move the card to `Stage = Review` (`cb723acb`) when opening the PR. On merge, GitHub flips `Status = Done`; manually move `Stage = Done` (`73062c96`).

## Filing a new task

When the user asks for new backlog work:

1. Confirm there isn't already an issue (`gh issue list --search "<keywords>"` in both repos).
2. Decide which repo owns it (or both → cross-repo).
3. Open the issue with title, body, and labels matching the taxonomy below.
4. Add to the Project board (`gh project item-add 1 --owner synthet --url <issue-url>`).
5. Set `Stage = Backlog` by default; promote to `Ready` only with maintainer signoff.

## Label taxonomy (identical in both repos)

| Family | Values |
|--------|--------|
| `area:*` | `python`, `db`, `gradio`, `electron`, `docs` |
| `priority:*` | `p0`, `p1`, `p2`, `p3` |
| `type:*` | `bug`, `feature`, `refactor`, `test`, `chore`, `epic` |
| (special) | `cross-repo` |
| (status) | `obsolete` — superseded/deferred; **stay open** on Backlog (not Ready) |

### Epics

- Parent issues use `type:epic` and link children via **GitHub sub-issues** (same repo).
- Cross-repo programs: one epic per repo + `cross-repo` label + counterpart URL in the body (sub-issues cannot span repos).
- Child titles may use `[#EPIC]` prefix for scanability.

### Obsolete (two tiers)

| Tier | When | Action |
|------|------|--------|
| **1 — dead** | Firebird-only, wrong repo, duplicate | **Close** + `wontfix` + comment; Project **Done** |
| **2 — superseded** | Icebox or replaced by React `/ui/` / REST | **Open** + `status:obsolete` + banner in body; Project **Backlog** |

Do **not** use `wontfix` for tier-2 obsolete-open items.

## Cross-repo work

When work touches both repos:

1. File one issue per repo (or use existing pair).
2. Apply `cross-repo` label to **both** issues.
3. Link counterparts in each issue body with the full URL.
4. Filter the board by `cross-repo` to see the pair.

The backend repo holds the canonical cross-repo coordination doc:
[`docs/technical/AGENT_COORDINATION.md`](../../../docs/technical/AGENT_COORDINATION.md).

## Reference IDs (for scripts)

| Thing | ID |
|-------|----|
| Project node id | `PVT_kwHOAFXgIs4BWC3c` |
| Project number | `1` |
| Owner | `synthet` (user-level) |
| `Stage` field id | `PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0` |
| `Backlog` option | `83b7a780` |
| `Ready` option | `ddaf7773` |
| `Claimed` option | `1cc70f0b` |
| `In Progress` option | `8b22e18e` |
| `Blocked` option | `4bbe5dd0` |
| `Review` option | `cb723acb` |
| `Done` option | `73062c96` |

Bootstrap scripts (idempotent — rerun safe):
- `scripts/bootstrap_labels.sh` — re-creates labels in both repos.
- `scripts/bootstrap_issues.py` — original migration from legacy `TODO.md`.
- `scripts/audit_backlog_issues.py` — read-only label/epic/obsolete gap report.
- `scripts/apply_backlog_inventory.py` — epics, label hygiene, obsolete tiers (`--apply`).
- `scripts/refine_issue_bodies.py` — align bodies with canonical docs.

Inventory snapshot: [`docs/project/backlog-inventory-2026-05.md`](../../../docs/project/backlog-inventory-2026-05.md).

## Don'ts

- **Don't** add tasks to `TODO.md` in either repo.
- **Don't** start work on an issue without claiming it (assignee + Stage transition).
- **Don't** silently abandon a `Claimed` or `In Progress` card — move to `Blocked` with a comment.
- **Don't** open a PR without `Closes #N` — the PR template will reject it.
- **Don't** skip Stage transitions ("I'll update the board later") — agents that drift make the queue lie about who's doing what.

## Mirrors

This skill is duplicated for parity in `.claude/skills/backlog-queue/SKILL.md` (Claude Code) and the same skill name lives in `image-scoring-gallery`. **Cursor** (this file) is canonical — keep them aligned. Tracking row in [`.agent/SKILL_INVENTORY.md`](../../../.agent/SKILL_INVENTORY.md).
