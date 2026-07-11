> **Cursor:** Same intent as Claude `/task-claim`. When customizing, keep in sync with `.claude/commands/task-claim.md`.

# /task-claim — claim a board issue and move it to Stage=Claimed

Use when starting work on a backlog item. Hand-off in `$ARGUMENTS` is the issue number (and optional repo).

**Usage:**
```
/task-claim <issue-number> [--repo backend|gallery]
```

If `--repo` is omitted, default to `backend` (this repo).

## Action

Run the steps below in order. Stop and report on any failure — do not proceed to the next step.

### 1. Resolve repo + verify the issue is claimable

```bash
REPO="image-scoring-backend"   # or image-scoring-gallery if --repo gallery
N="<issue-number>"

gh issue view "$N" --repo "synthet/$REPO" --json number,state,assignees,title
```

If `state == "CLOSED"`, abort: report "issue is closed".
If `assignees` is non-empty and you are not in it, abort: report who has it.

### 2. Assign yourself

```bash
gh issue edit "$N" --repo "synthet/$REPO" --add-assignee @me
```

### 3. Find the project item id

```bash
ITEM_ID=$(gh project item-list 1 --owner synthet --format json --limit 200 \
  | jq -r --argjson n "$N" --arg repo "$REPO" '
      .items[]
      | select(.content.number == $n)
      | select((.content.repository // "") | endswith($repo))
      | .id')

if [ -z "$ITEM_ID" ]; then
  echo "ERROR: issue #$N is not on the Project board (https://github.com/users/synthet/projects/1)"
  exit 1
fi
```

### 4. Move the card to `Stage = Claimed`

```bash
gh project item-edit \
  --id "$ITEM_ID" \
  --project-id PVT_kwHOAFXgIs4BWC3c \
  --field-id PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0 \
  --single-select-option-id 1cc70f0b
```

### 5. Confirm + remind

Report back:

- Issue URL: `https://github.com/synthet/$REPO/issues/$N`
- Title (from step 1)
- "Claimed. Move to `Stage = In Progress` (option id `8b22e18e`) on your first commit. PR description must include `Closes #$N`."

## Reference IDs

| Thing | ID |
|-------|----|
| Project node id | `PVT_kwHOAFXgIs4BWC3c` |
| Stage field id | `PVTSSF_lAHOAFXgIs4BWC3czhRaNZ0` |
| Backlog | `83b7a780` |
| Ready | `ddaf7773` |
| Claimed | `1cc70f0b` |
| In Progress | `8b22e18e` |
| Blocked | `4bbe5dd0` |
| Review | `cb723acb` |
| Done | `73062c96` |

Full contract: [`docs/project/00-backlog-workflow.md`](../../docs/project/00-backlog-workflow.md) and skill [`.cursor/skills/backlog-queue/SKILL.md`](../skills/backlog-queue/SKILL.md).
