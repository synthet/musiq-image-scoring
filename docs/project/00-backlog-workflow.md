# Backlog workflow — picking tasks, tracking status, and keeping docs aligned

This document is the **operating guide** for the Python backend backlog. The gallery repo uses the same structure: **[`docs/project/00-backlog-workflow.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/project/00-backlog-workflow.md)** is canonical there; [`BACKLOG_GOVERNANCE.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/project/BACKLOG_GOVERNANCE.md) is an alias. Here **`00-backlog-workflow.md`** is canonical; [`BACKLOG_GOVERNANCE.md`](BACKLOG_GOVERNANCE.md) is an alias for backward links.

It complements the task lists (`TODO.md`, mirrors below) by describing *how* to choose work, record progress, and avoid documentation drift.

---

## 1. Where things live (single hierarchy)

| Role | Location | Purpose |
|------|----------|---------|
| **Canonical backlog** | [`TODO.md`](../../TODO.md) (repo root) | Master checklist, counts, markers, **Highest-Impact Next Steps** |
| **API slice** | [`../reference/api/TODO.md`](../reference/api/TODO.md) | Pointer to root backlog + contract links (no duplicate checkboxes) |
| **Embedding slice** | [`../features/planned/embeddings/TODO.md`](../features/planned/embeddings/TODO.md) | Pointer to root backlog + embedding `NEXT_STEPS` |
| **Archived pointer** | [`TODO.md`](TODO.md) | Historical index; do not add tasks here |
| **Database track (status narrative)** | [`../planning/database/NEXT_STEPS.md`](../planning/database/NEXT_STEPS.md) | Phase 4 verification steps; not a second backlog |
| **Embedding track (status narrative)** | [`../features/planned/embeddings/NEXT_STEPS.md`](../features/planned/embeddings/NEXT_STEPS.md) | Implementation vs UX gaps |
| **Migration (historical + decisions)** | [`../planning/database/FIREBIRD_POSTGRES_MIGRATION.md`](../planning/database/FIREBIRD_POSTGRES_MIGRATION.md) | Postgres cutover narrative |

**Rule:** Edit **[`TODO.md`](../../TODO.md) first**. Then propagate changes down the sync order (next section). Do not invent parallel sources of truth.

---

## 2. Sync order (after any status change)

When you complete, reopen, split, or reprioritize a task:

1. Update **[`TODO.md`](../../TODO.md)** — checkboxes, **Last evaluated** date, count snapshot, **Highest-Impact Next Steps** if order changed.
2. Skim **[`docs/planning/database/NEXT_STEPS.md`](../planning/database/NEXT_STEPS.md)** and **[`docs/features/planned/embeddings/NEXT_STEPS.md`](../features/planned/embeddings/NEXT_STEPS.md)** — adjust only if the track’s true status changed (not every small fix).
3. If REST/OpenAPI/contract rows moved, ensure **[`docs/technical/API_CONTRACT.md`](../technical/API_CONTRACT.md)** / [`openapi.yaml`](../reference/api/openapi.yaml) / [`API.md`](../reference/api/API.md) are updated in the same PR when behavior changes.
4. If the Electron app is affected, follow **[`AGENT_COORDINATION.md`](../technical/AGENT_COORDINATION.md)** and sync with **image-scoring-gallery** [`TODO.md`](https://github.com/synthet/image-scoring-gallery/blob/main/TODO.md) and [`docs/project/00-backlog-workflow.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/project/00-backlog-workflow.md) (mirror sync order).
5. If the PR touches open backlog items, complete **[`.github/pull_request_template.md`](../../.github/pull_request_template.md)** when that file exists (TODO sync, counts).

**Cadence:** Reconcile `TODO.md` with plan docs **at least weekly** and **immediately** after merging work that changes open items.

---

## 3. How to pick the next task (step-by-step)

### Step A — Check the recommended sequence

Read **“Highest-Impact Next Steps”** in [`TODO.md`](../../TODO.md). That block is ordered for impact and cross-repo dependency (coordination with the gallery repo, schema work, verification debt).

### Step B — Apply dependency gates

- **`[Electron]`:** Requires changes in **image-scoring-gallery** (or coordinated contract). Confirm API/events exist in this repo or schedule a joint change per [Agent Coordination](../technical/AGENT_COORDINATION.md).
- **`[Gradio]`:** WebUI / operator flows in this repo.
- **`[Python]`:** Backend modules, FastAPI, tests.
- **`[DB]`:** PostgreSQL schema, Alembic, `modules/db.py` / `db_postgres.py`.
- **Blocked?** Prefer a **[Python]**/**[Gradio]**-only item or document the blocker on the relevant line.

### Step C — Size the work

- Large themes get a short design note or issue; keep **one** line in [`TODO.md`](../../TODO.md) as the anchor unless you split into sub-tasks with checkboxes.
- Smaller fixes stay as single lines under the existing priority sections.

### Step D — Track execution status

- Use **checkboxes** in [`TODO.md`](../../TODO.md) (`- [ ]` / `- [x]`).
- For multi-session work, optionally use **mcp-kanban** (see [`.cursor/skills/mcp-kanban-workflow`](../../.cursor/skills/mcp-kanban-workflow/SKILL.md)) — markdown remains authoritative.

---

## 4. Count snapshot rules (brief)

When you update totals in [`TODO.md`](../../TODO.md):

- **Open item:** each unchecked `- [ ]` line counts as one.
- **Gallery-dependent:** any open line tagged **`[Electron]`** (work in image-scoring-gallery or coordinated across repos).
- **Backend scope:** open items **without** `[Electron]` (this repo only, including `[Python]` / `[Gradio]` / `[DB]`).

Full rules and the live snapshot live in the **Count Snapshot Rules** and **Current Status Snapshot** sections of [`TODO.md`](../../TODO.md).

---

## 5. Related reading

- [Documentation index](../INDEX.md)
- [Database NEXT_STEPS](../planning/database/NEXT_STEPS.md) · [Embedding NEXT_STEPS](../features/planned/embeddings/NEXT_STEPS.md)
- [Periodic backlog review notes](../reports/project-reviews/UNFINISHED_BUSINESS_EVALUATION_2026-03-14.md)
- Gallery sibling workflow: [**image-scoring-gallery** — `docs/project/00-backlog-workflow.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/project/00-backlog-workflow.md) ([`BACKLOG_GOVERNANCE.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/project/BACKLOG_GOVERNANCE.md) is an alias)

[← Project planning index](INDEX.md)
