# Backlog workflow — claiming work, tracking status, keeping the queue truthful

The canonical task queue is the **GitHub Project board**:

**→ https://github.com/users/synthet/projects/1**

It surfaces issues from both repos:
- `synthet/image-scoring-backend` (this repo) — backend, FastAPI, DB schema
- `synthet/image-scoring-gallery` — Electron / React UI

This document is the **operating contract** every agent (human or AI) must follow
when picking and tracking work. The gallery repo has the same doc — both must stay
in sync.

---

## 1. The board

Two single-select fields drive the workflow:

| Field | Purpose |
|-------|---------|
| **`Stage`** *(primary, custom)* | `Backlog → Ready → Claimed → In Progress → Blocked → Review → Done` — the operator queue every agent reads from and writes to. |
| **`Status`** *(built-in)* | `Todo / In Progress / Done` — required by GitHub PR-close automation; flips to `Done` when a PR with `Closes #N` merges. |

Labels are facets:

| Family | Values |
|--------|--------|
| `area:*` | `python`, `db`, `gradio`, `electron`, `docs` |
| `priority:*` | `p0`, `p1`, `p2`, `p3` |
| `type:*` | `bug`, `feature`, `refactor`, `test`, `chore`, `epic` |
| (special) | `cross-repo` |
| (status) | `obsolete` — superseded or icebox; keep open, Stage = Backlog |

**Epics:** `type:epic` parents with GitHub sub-issues (same repo). Cross-repo epics are paired issues with URLs in the body.

**Obsolete:** Close + `wontfix` when work is dead (e.g. Firebird-only); use `status:obsolete` when superseded but kept for history. See [`backlog-inventory-2026-05.md`](backlog-inventory-2026-05.md).

**Rule:** Edit issues, not files. The repo `TODO.md` is a pointer only.

---

## 2. The agent contract

Every contributor — human or AI — follows the same five steps. Do **all** of them; skipping a step puts the queue out of sync.

### Step 1 — Pick from `Ready`

Open the [Project board](https://github.com/users/synthet/projects/1), filter to **Stage = Ready**, sort by `priority:p0..p3`. Pick the highest-priority unassigned card.

> If `Ready` is empty, ask the maintainer to promote items from `Backlog`. Do not invent new work.

### Step 2 — Claim it

Either run the slash command (Claude Code):

```
/task-claim <issue-number>
```

Or run the equivalent `gh` commands manually:

```bash
# Replace <N> with the issue number, <repo> with image-scoring-backend or image-scoring-gallery
gh issue edit <N> --repo synthet/<repo> --add-assignee @me

# Move the card to Claimed
ITEM_ID=$(gh project item-list 1 --owner synthet --format json \
  --limit 200 \
  | jq -r --argjson n <N> --arg repo "<repo>" \
      '.items[] | select(.content.number==$n and (.content.repository|endswith($repo))) | .id')

gh project item-edit \
  --id "$ITEM_ID" \
  --project-id PVT_kwHOAFXgIs4BWC3c \
  --field-id PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0 \
  --single-select-option-id 1cc70f0b   # Claimed
```

### Step 3 — Flip to `In Progress` on first commit

When you push your first commit on the work branch, move the card to `In Progress`:

```bash
gh project item-edit \
  --id "$ITEM_ID" \
  --project-id PVT_kwHOAFXgIs4BWC3c \
  --field-id PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0 \
  --single-select-option-id 8b22e18e   # In Progress
```

### Step 4 — If blocked, say so

If you hit an external dependency, missing decision, or upstream bug:

1. Move the card to `Stage = Blocked` (option id `4bbe5dd0`).
2. Comment on the issue describing **what** is blocking and **what would unblock it**.

```bash
gh issue comment <N> --repo synthet/<repo> --body "Blocked: <one-line reason + what would unblock>."
```

### Step 5 — Reference the issue in your PR

Your PR description **must** contain a line of the form:

```
Closes #<N>
```

That triggers GitHub's PR-close automation: on merge, the issue closes and the
card moves to `Status = Done`. Move the card to `Stage = Review` while the PR is
open, then to `Stage = Done` after merge (the automation handles `Status` but
the custom `Stage` field is manual).

The PR template enforces an `Issue:` line — see
[`.github/pull_request_template.md`](../../.github/pull_request_template.md).

---

## 3. Cross-repo work

When work touches both repos:

1. File one issue in **each** repo (or use existing pair).
2. Apply the `cross-repo` label to both.
3. In each issue body, link to the counterpart with the full URL.
4. The Project board shows both — group/filter by `cross-repo` to see the pair.

See [`docs/technical/AGENT_COORDINATION.md`](../technical/AGENT_COORDINATION.md)
for cross-repo sync protocol details (API contract changes, schema renames, etc.).

---

## 4. Where things live

| Role | Location |
|------|----------|
| **Canonical queue** | [Project board](https://github.com/users/synthet/projects/1) |
| **Issue trackers** | [backend issues](https://github.com/synthet/image-scoring-backend/issues), [gallery issues](https://github.com/synthet/image-scoring-gallery/issues) |
| **Pointer (this repo)** | [`TODO.md`](../../TODO.md) |
| **Pointer (gallery)** | [gallery `TODO.md`](https://github.com/synthet/image-scoring-gallery/blob/main/TODO.md) |
| **This contract** | here, plus [gallery sibling](https://github.com/synthet/image-scoring-gallery/blob/main/docs/project/00-backlog-workflow.md) |
| **Status narratives** | [`docs/planning/database/NEXT_STEPS.md`](../planning/database/NEXT_STEPS.md), [`docs/features/planned/embeddings/NEXT_STEPS.md`](../features/planned/embeddings/NEXT_STEPS.md) — narrative, not a backlog |

---

## 5. Reference: project + field IDs

For automation/scripts:

| Thing | ID |
|-------|----|
| Project node id | `PVT_kwHOAFXgIs4BWC3c` |
| Project number | `1` |
| Owner | `synthet` (user) |
| `Stage` field id | `PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0` |
| `Backlog` option | `83b7a780` |
| `Ready` option | `ddaf7773` |
| `Claimed` option | `1cc70f0b` |
| `In Progress` option | `8b22e18e` |
| `Blocked` option | `4bbe5dd0` |
| `Review` option | `cb723acb` |
| `Done` option | `73062c96` |

Bootstrap scripts:
- [`scripts/bootstrap_labels.sh`](../../scripts/bootstrap_labels.sh) — re-create the label taxonomy in both repos.
- [`scripts/bootstrap_issues.py`](../../scripts/bootstrap_issues.py) — original migration from legacy `TODO.md`; idempotent (skips by title).
