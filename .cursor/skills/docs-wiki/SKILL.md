---
name: docs-wiki
description: >-
  Maintain image-scoring-backend docs/ as an OKF-aligned wiki: frontmatter,
  planning vs features/planned, guides, architecture, indexes, and log.
  Triggers: wiki maintenance, docs update, documentation audit, wiki ingest/lint/query.
---

# Backend docs wiki skill

## When to apply

- Slash commands `/wiki-ingest`, `/wiki-query`, `/wiki-lint` (`.cursor/commands/` and `.claude/commands/`)
- Any task that adds, materially edits, renames, or reorganizes files under `docs/`

## Read first

| File | Role |
|------|------|
| [`docs/OKF_ADOPTION.md`](../../docs/OKF_ADOPTION.md) | Local OKF frontmatter profile, type vocabulary, migration policy |
| [`docs/WIKI_SCHEMA.md`](../../docs/WIKI_SCHEMA.md) | Folder taxonomy, naming, log format |
| [`docs/CANONICAL_SOURCES.md`](../../docs/CANONICAL_SOURCES.md) | API, schema, pipeline vocabulary authority |
| [`docs/INDEX.md`](../../docs/INDEX.md) | Master index |

## Folder map (short)

- **`docs/planning/`** — migrations, Phase 4/5 DB work, refactors
- **`docs/features/planned/`** — product/UI specs (includes `embeddings/`)
- **`docs/guides/`** — getting started + setup
- **`docs/architecture/`** — system overview and pipeline diagrams
- **`docs/technical/`** — stable UPPER_CASE reference pages
- **`docs/reports/`** — point-in-time audits and synthesis pages

## OKF requirements

- Treat `docs/` as the repository's OKF-aligned knowledge bundle.
- New living docs and materially edited living docs should add YAML frontmatter with at least `type`; prefer `title`, `description`, `resource`, `tags`, `timestamp`, and `okf_version: 0.1`.
- Use the type vocabulary in `docs/OKF_ADOPTION.md` when possible; consumers must tolerate unknown clear human-readable `type` values.
- Avoid bulk metadata-only churn in archived or untouched docs; add OKF metadata opportunistically when content changes.

After substantive wiki edits, update the relevant `INDEX.md` files and append `docs/log.md`.

## Rule

Glob-scoped guidance: [`.cursor/rules/documentation.mdc`](../../rules/documentation.mdc).
