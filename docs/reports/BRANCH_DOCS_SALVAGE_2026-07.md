---
type: Report
title: Branch cleanup and docs-only salvage (July 2026)
description: Cross-repo branch audit outcome; gallery docs-only branches archived and deleted; backend UNMERGED branches with code retained.
resource: docs/reports/BRANCH_DOCS_SALVAGE_2026-07.md
tags: [reports, housekeeping, branch-cleanup, cross-repo]
timestamp: 2026-07-01T00:00:00Z
okf_version: 0.1
---

# Branch cleanup and docs-only salvage (July 2026)

Summary of the July 2026 branch audit across **image-scoring-backend** (`master`) and **image-scoring-gallery** (`main`).

**Gallery ingest detail:** [09-branch-docs-salvage-2026-07.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/reports/09-branch-docs-salvage-2026-07.md)

## Phase 1 completed (merged / stale)

Previously deleted: **13** backend + **6** gallery remote branches whose tips were fully merged or squash-equivalent to default, plus **23** local stale branches.

## Docs-only branches (gallery)

| Branch | Action |
|--------|--------|
| `housekeeping/g4-docs-wiki` | Patches archived; remote deleted — content already on `main` |
| `codex/restructure-docs-using-open-knowledge-format-cmv38j` | Patches archived; remote deleted — OKF pass landed via PR #145 |

## Backend docs-only candidates

| Branch | Verdict |
|--------|---------|
| `housekeeping/b6-docs-wiki-lint` | **Retained** — includes `scripts/wiki_lint_scan.py` (code), not docs-only |

## UNMERGED branches retained (code / mixed)

### Backend (`master`)

- `claude/llm-wiki-review-oy0y71` — agent scaffolding
- `codex/add-conflict-marker-check-to-repository` — CI script
- `codex/add-inspector-links-for-images` (+ duplicate `83b2bz`) — frontend inspector links
- `codex/add-testing-documentation-and-coverage-setup` — CI + docs
- `codex/refactor-ci-jobs-and-update-documentation` — CI refactor
- `codex/work-on-next-github-task` (+ `6zkn76`) — input-size study script
- `feat/mcp-search-dispatch-pr1` — MCP compact dispatch follow-ups
- `housekeeping/b6-docs-wiki-lint` — wiki lint script + doc fixes

### Gallery (`main`)

- `claude/agentic-framework-improvements-qa839w` — agent infra + CI
- `claude/cross-repo-sync-backend-api-DWyq4` — OpenAPI sync
- `claude/next-github-task-vzaps1` — reveal-in-explorer fix
- `codex/disable-find-similar-images-feature` — UI + contract checks
- `codex/fix-issues-in-backup-feature-specification` — backup modal
- `codex/remove-duplicates-and-embeddings-from-tools-submenu` — menu + OpenAPI
- `codex/task-title-0bwetz` — config tests
- `feat/gallery-mcp-search-dispatch` — MCP router WIP
- `housekeeping/g4-docs-wiki` — **deleted** (docs-only)
- `codex/restructure-docs-using-open-knowledge-format-cmv38j` — **deleted** (docs-only)

## Local review

- **Backend:** `feat/clip-quality-culling` (local only) — confirm before deleting; PR #272 merged.

## Follow-ups

1. Cherry-pick or drop tip commits on “merged PR but UNMERGED tip” branches (`feat/mcp-search-dispatch-pr1`, `housekeeping/b6-docs-wiki-lint`).
2. Enable **delete branch on merge** on both GitHub repos.
3. Re-run audit quarterly (`git fetch --prune` + cherry vs default).
