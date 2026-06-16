---
type: Documentation Schema
title: Wiki Schema
description: Documentation structure, naming, link, metadata, and maintenance conventions.
resource: WIKI_SCHEMA.md
tags: [docs, schema, okf, maintenance]
timestamp: 2026-06-16T00:00:00Z
okf_version: 0.1
---

# Wiki schema — image-scoring-backend `docs/`

This repository keeps `docs/` as an LLM-maintained wiki: small pages, clear hubs, and stable links to canonical contracts.


## OKF alignment

`docs/` is maintained as an [Open Knowledge Format adoption bundle](OKF_ADOPTION.md): markdown files with YAML frontmatter, stable relative paths as concept identities, relative markdown links as the knowledge graph, folder `INDEX.md` hubs, and append-only `log.md` history.

New living pages and materially edited living pages should include YAML frontmatter with at least `type`; recommended fields are `title`, `description`, `resource`, `tags`, `timestamp`, and `okf_version`. See [OKF_ADOPTION.md](OKF_ADOPTION.md) for the local type vocabulary and migration policy.

## Page types and folders

| Folder | Purpose |
|--------|---------|
| [`architecture/`](architecture/) | System overview, pipeline diagrams, connector proposals |
| [`guides/getting-started/`](guides/getting-started/) | New-user and operator how-tos |
| [`guides/setup/`](guides/setup/) | Windows, WSL, CUDA, Docker, environments |
| [`features/planned/`](features/planned/) | Product/UI specs not yet shipped (includes `embeddings/`) |
| [`features/implemented/`](features/implemented/) | Shipped behavior catalog (routing + pointers; not a second technical manual) |
| [`planning/`](planning/) | Migrations, schema phases, refactors, model roadmaps |
| [`technical/`](technical/) | Stable reference (UPPER_CASE filenames): API, DB, MCP, feature deep-dives |
| [`reference/`](reference/) | API artifacts, model weight notes |
| [`reports/`](reports/) | Point-in-time audits and research |
| [`archive/`](archive/) | Deprecated or superseded material (keep for history) |
| [`project/`](project/) | Backlog workflow and governance pointers |
| [`testing/`](testing/) | Test status and WSL marker docs |

### Repo root hub pages (`docs/*.md`)

Short entry-point guides at the **root of `docs/`** (not in a subfolder): **DEVELOPMENT**, **TESTING**, **TROUBLESHOOTING**, **DIAGNOSTICS**, **DATABASE**, **ARCHITECTURE**, **IMAGE_PIPELINE**, **EXPORT_PIPELINE**, **EMBEDDINGS**. They summarize where to look and link into `technical/`, `guides/`, `architecture/`, and scripts. Prefer keeping them **thin**; deep reference stays in `technical/` and `reference/`.

## Naming

- **New pages:** prefer `kebab-case.md` in `guides/`, `features/planned/`, and `architecture/`.
- **Legacy technical reference:** keep existing `UPPER_CASE.md` names under `technical/` to avoid churn.
- **Reports:** include a date in the filename when the note is a snapshot (`topic-YYYY-MM-DD.md`).

## Links

- Use **relative** links from the page you are editing.
- Prefer linking to **[`CANONICAL_SOURCES.md`](CANONICAL_SOURCES.md)** from agent-oriented prose when pointing at contracts.
- **Cross-repo:** use full GitHub URLs to **image-scoring-gallery** when the canonical doc lives there.

## Indexes and activity log

After adding, renaming, or removing pages:

1. Update the nearest folder `INDEX.md` and, when relevant, [`INDEX.md`](INDEX.md) and [`README.md`](README.md).
2. Append a line to [`log.md`](log.md) under the current month heading using:  
   `- YYYY-MM-DD: <verb> — <details and paths>`  
   Verbs: `ingested`, `created`, `updated`, `lint-fixed`, `filed-back`, `reorganized`.

## Slash commands

Project commands under `.cursor/commands/` and `.claude/commands/` (`wiki-ingest`, `wiki-query`, `wiki-lint`) should read this file before large wiki edits.
