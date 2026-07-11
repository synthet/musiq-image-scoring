---
name: agent-git-workflows
description: >-
  Safe git and GitHub CLI workflows — status, bounded diffs, gh issues/PRs.
  Use before commits, when reviewing changes, or for backlog/PR operations.
  Destructive git commands require user confirmation.
---

# Agent git workflows

## Purpose

Inspect and modify version control state with bounded diffs. Align with cross-repo backlog contract (`/task-claim`, `Closes #N` in PRs).

## When to use

- Before any edit: check working tree
- Before commit/PR: review `git diff --stat` and focused hunks
- GitHub issues, PR status, project board via `gh`
- Secret scan before sharing diffs (optional `gitleaks`)

## Required tools

`git`, `gh`, optional `delta`, optional `gitleaks`

Install: [agent-cli-hub/references/install-blocks.md](../agent-cli-hub/references/install-blocks.md)

## Common commands

### Before editing

```bash
git status --short
git branch -vv
```

### Review changes

```bash
git diff --stat
git diff -- electron/main.ts | delta
git log -5 --oneline
```

### GitHub CLI

```bash
gh issue view 123
gh pr status
gh pr create --title "..." --body "Closes #123"
```

PowerShell:

```powershell
git status --short
git diff --stat
gh pr status
```

## Agent-safe patterns

1. Always `git status --short` before edits.
2. Show `git diff --stat` and path-scoped `git diff` before claiming work complete.
3. Never modify `.git/config` (project rule).
4. PR body must include `Closes #<N>` per backlog contract — see [`backlog-queue`](../backlog-queue/SKILL.md).
5. Only commit when the user explicitly asks.

## Commands requiring confirmation

**Always confirm:** `git clean`, `git reset --hard`, `git push --force`, `git filter-repo`, interactive rebase, branch delete on shared remotes.

Full list: [commands-requiring-confirmation.md](../agent-cli-hub/references/commands-requiring-confirmation.md).

## Troubleshooting

- **`gh` not authenticated:** `gh auth login`
- **Line ending noise on Windows:** check `.gitattributes`; avoid mixed WSL/Windows edits on same checkout
- **Large diff:** use `git diff --stat` first, then per-file diffs

## Verification checklist

```bash
git --version && gh --version
git status --short
```
