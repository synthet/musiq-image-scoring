---
name: codebase-size-audit
description: >-
  Read-only scan for files ≥1000 LoC and functions/methods ≥150 LoC across
  image-scoring-backend and image-scoring-gallery. Produces a markdown or JSON
  report with refactor priority hints. Use when the user asks for a codebase size
  audit, large file scan, god-module review, or refactoring hotspot analysis.
---

# Codebase size audit

Read-only. **Do not edit production code** unless the user explicitly asks to implement refactors after reviewing the report.

## Defaults

| Threshold | Value | Meaning |
|-----------|------:|---------|
| `--file-min` | 1000 | Flag whole source files at or above this line count |
| `--fn-min` | 150 | Flag functions/methods at or above this span |

Skips: `node_modules`, venvs, `dist*`, `__pycache__`, `FirebirdLinux`, `static` bundles, generated `*.generated.ts`.

## Run (canonical script)

From **image-scoring-backend** root (Python 3.10+; no venv required):

```bash
# Backend only
python scripts/audit/codebase_size_audit.py

# Gallery sibling (adjust path if clones differ)
python scripts/audit/codebase_size_audit.py --root ../image-scoring-gallery

# Save combined workflow — backend then gallery
python scripts/audit/codebase_size_audit.py -o .agent/scratch/audit-backend.md
python scripts/audit/codebase_size_audit.py --root ../image-scoring-gallery -o .agent/scratch/audit-gallery.md
```

JSON for tooling:

```bash
python scripts/audit/codebase_size_audit.py --format json -o .agent/scratch/audit-backend.json
```

Custom thresholds:

```bash
python scripts/audit/codebase_size_audit.py --file-min 800 --fn-min 120
```

## Report template (agent summary)

After running the script, present:

```markdown
# Codebase size audit — YYYY-MM-DD

## Backend (≥1000 LoC files)
| Lines | Path | Notes |
...

## Gallery (≥1000 LoC files)
...

## Top functions (≥150 LoC) — both repos
Top 10–15 by line count with path and symbol.

## Batch 1 status (if re-auditing)
- api.py / mcp_server.py / main.ts — note post-extraction line counts vs prior audit.

## Suggested next extractions (safe-first)
1. …
2. …
```

## Refactor guidance (Vexlum / Driftara)

**Safe extraction (low contract risk):**

- Backend: sibling modules + re-exports (`api_helpers`, `mcp/tools/*`); keep import paths stable.
- Gallery: `electron/ipc/register*.ts`; **never** rename IPC channel strings or change preload without coordinated PR.

**Defer (higher risk):**

- `modules/db_legacy.py` domain decomposition — schema/connector coupling.
- `create_api_router` domain routers — OpenAPI route order and test matrix.
- `electron/db.ts` — IPC result shapes tied to renderer.
- `ImageViewer.tsx` / `AppContent.tsx` — extract hooks incrementally with Vitest coverage.

**Cross-repo:** file issues on GitHub Project board before large refactors; cite `docs/project/00-backlog-workflow.md`.

## Related

- Prior plan: Batch 1 safe extractions (api helpers/models, MCP tools, gallery IPC).
- Backend tests after extractions: `pytest` API + MCP subsets per `AGENTS.md`.
- Gallery: `npm run test:run`, `npx tsc -p electron/tsconfig.json --noEmit`.
