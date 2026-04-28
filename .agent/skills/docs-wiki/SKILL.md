---
name: docs-wiki-backend
description: >-
  Maintain image-scoring-backend docs/ as a wiki: planning vs features/planned,
  guides, architecture, indexes, and log. Triggers: wiki ingest/lint/query,
  documentation audit, doc-only PRs.
---

# Backend docs wiki skill

## When to apply

- Slash commands `/wiki-ingest`, `/wiki-query`, `/wiki-lint` (see `.cursor/commands/` and `.claude/commands/`)
- Any task that adds, renames, or reorganizes files under `docs/`

## Read first

| File | Role |
|------|------|
| [`docs/WIKI_SCHEMA.md`](../../docs/WIKI_SCHEMA.md) | Folder taxonomy, naming, log format |
| [`docs/CANONICAL_SOURCES.md`](../../docs/CANONICAL_SOURCES.md) | API, schema, pipeline vocabulary authority |
| [`docs/INDEX.md`](../../docs/INDEX.md) | Master index |

## Folder map (short)

- **`docs/planning/`** — migrations, Phase 4/5 DB work, refactors
- **`docs/features/planned/`** — product/UI specs (includes `embeddings/`)
- **`docs/guides/`** — getting started + setup
- **`docs/architecture/`** — system overview and pipeline diagrams
- **`docs/technical/`** — stable UPPER_CASE reference pages

After substantive wiki edits, update the relevant `INDEX.md` files and append `docs/log.md`.
