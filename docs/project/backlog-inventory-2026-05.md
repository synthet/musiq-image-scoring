# Backlog inventory snapshot — 2026-05-20

Point-in-time record after the GitHub backlog inventory pass. **Live queue:** [Project board #1](https://github.com/users/synthet/projects/1).

## Summary

| Repo | Open issues (approx.) | New epics | Closed (tier-1) | Obsolete-open (tier-2) |
|------|----------------------|-----------|-----------------|------------------------|
| image-scoring-backend | 90+ | #198–#203 | #145, #122, #123 | #102, #117, #124–#130 |
| image-scoring-gallery | 30+ | #108–#110 | #111, #112 (dupes) | #73 |

## New epic parents (2026-05-20)

### Backend

| Epic | Children |
|------|----------|
| [#198](https://github.com/synthet/image-scoring-backend/issues/198) Architecture hardening | #169–#175 |
| [#199](https://github.com/synthet/image-scoring-backend/issues/199) Embedding Atlas UX | #134–#142 |
| [#200](https://github.com/synthet/image-scoring-backend/issues/200) RAW preview QA | #104–#108 |
| [#201](https://github.com/synthet/image-scoring-backend/issues/201) AI culling XMP verification | #109–#110 |
| [#202](https://github.com/synthet/image-scoring-backend/issues/202) Run lifecycle bugs | #156–#157, #161, #163–#166 |
| [#203](https://github.com/synthet/image-scoring-backend/issues/203) Codex branch triage | #192–#197 |

### Gallery

| Epic | Children |
|------|----------|
| [#108](https://github.com/synthet/image-scoring-gallery/issues/108) Embeddings & similarity UI | #73–#79 |
| [#109](https://github.com/synthet/image-scoring-gallery/issues/109) API/contract hardening | #87–#91 (links backend #174) |
| [#110](https://github.com/synthet/image-scoring-gallery/issues/110) Codex branch triage | #103–#106 |

## Formalized existing epics

| Parent | Children |
|--------|----------|
| Backend #118 | #150–#155 |
| Backend #143 | #144–#149 ( #145 closed wontfix ) |
| Backend #180 | #181–#191 |
| Gallery #94 | #95–#102 (counterpart #180) |

## Obsolete handling applied

**Tier 1 (closed):**

- #145 — Firebird DDL for `image_technical_failures` (Postgres-only)
- Backend #122, #123 — mis-filed gallery UX → gallery #113, #114

**Tier 2 (`status:obsolete`, open):**

- Backend #102, #117, #124–#130
- Gallery #73 — IPC/WebSocket bridge superseded by REST `apiService`

## Architecture notes for agents

- **Primary DB:** PostgreSQL + pgvector
- **Primary UI:** React `/ui/`; Gradio `/app` is operator-only
- **Gallery:** Electron + `electron/db.ts` / `apiService.ts`

## Scripts

```bash
python scripts/audit_backlog_issues.py
python scripts/apply_backlog_inventory.py          # dry-run
python scripts/apply_backlog_inventory.py --apply  # mutating
python scripts/refine_issue_bodies.py
```

## Related docs

- [00-backlog-workflow.md](00-backlog-workflow.md)
- [CANONICAL_SOURCES.md](../CANONICAL_SOURCES.md)
- [PIPELINE_TERMINOLOGY.md](../technical/PIPELINE_TERMINOLOGY.md)
