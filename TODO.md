# Backlog

> The canonical task queue is the GitHub Project board.
>
> **→ https://github.com/users/synthet/projects/1**

This file is preserved as a pointer only. **Do not add tasks here** — open an issue
in the appropriate repo and let the Project automation pick it up.

## How to use the queue

1. Pick a card from the **`Ready`** column on the board.
2. Run `/task-claim <issue-number>` (or the manual `gh` commands in
   [`docs/project/00-backlog-workflow.md`](docs/project/00-backlog-workflow.md))
   to assign yourself and move the card to **`Claimed`**.
3. Move the card to **`In Progress`** on your first commit.
4. In your PR description include `Closes #<n>`. Merging the PR will auto-move
   the card to **`Done`**.

## Filters and counts

The board has two single-select fields you can group/filter by:

- **`Status`** (built-in): Todo / In Progress / Done — used by GitHub automation.
- **`Stage`** (custom, primary): `Backlog → Ready → Claimed → In Progress → Blocked → Review → Done` — the operator queue.

Plus labels: `area:python | area:db | area:gradio | area:electron | area:docs`,
`priority:p0..p3`, `type:bug|feature|refactor|test|chore`, `cross-repo`.

## Cross-repo work

`[Electron]` items live in the sibling repo
[`image-scoring-gallery`](https://github.com/synthet/image-scoring-gallery).
The same Project board surfaces issues from both repos; coordinated changes
carry the `cross-repo` label on both sides.

See [`docs/technical/AGENT_COORDINATION.md`](docs/technical/AGENT_COORDINATION.md)
for the cross-repo sync protocol.
