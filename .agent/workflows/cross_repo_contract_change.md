---
description: Cross-repo contract change — backend first, then gallery
---

## Purpose

Change **API**, **schema**, or **pipeline terminology** without breaking **Driftara Gallery** or docs drift.

## When to use

- Any REST path/field change, DB column visible to gallery SQL/API mode, or user-facing pipeline label change.

## Canonical docs (read first)

- [docs/CANONICAL_SOURCES.md](../../docs/CANONICAL_SOURCES.md)
- [docs/technical/AGENT_COORDINATION.md](../../docs/technical/AGENT_COORDINATION.md)
- Gallery: [docs/CANONICAL_SOURCES.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/CANONICAL_SOURCES.md)
- Gallery integration follow-ups: [docs/integration/TODO.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/integration/TODO.md)

## Steps (strict order)

1. **Backend canonical contract** — identify or update `docs/technical/API_CONTRACT.md`, `docs/reference/api/openapi.yaml`, `docs/technical/DB_SCHEMA.md`, `docs/technical/PIPELINE_TERMINOLOGY.md` as applicable **before** or **with** code (never ship code contradicted by written contract).
2. **Backend implementation** — `modules/api.py`, `modules/db_postgres.py`, migrations, phases as needed.
3. **Backend tests** — targeted pytest; markers per [docs/TESTING.md](../../docs/TESTING.md).
4. **Backend docs pass** — AGENT_COORDINATION.md if coordination/process changes; append [docs/log.md](../../docs/log.md).
5. **Gallery integration** — sibling repo: `electron/apiService.ts`, IPC/preload types if payloads change, `src/constants/pipelineLabels.ts` / types, [docs/integration/TODO.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/integration/TODO.md) if work remains.
6. **Backend checks** — doctor, fast pytest subset (see [.agent/COMMANDS.md](../COMMANDS.md)).
7. **Gallery checks** — `npm run doctor`, `npx tsc --noEmit`, `npx tsc -p electron/tsconfig.json --noEmit`, `npm run lint`, `npm run contract:check` as appropriate.
8. **Handoff note** — one short paragraph in PR or issue: what changed, which repos touched, which commands were run.

## Do not

- Do not change gallery-only first for backend-owned fields.
- Do not merge without updating canonical docs or `docs/log.md` when user-visible or integration-visible behavior changed.

**Repo:** This file lives in **image-scoring-backend** — mirror copy exists in **image-scoring-gallery** `.agent/workflows/` with the same steps.
