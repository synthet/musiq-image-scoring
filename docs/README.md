# Documentation

Complete documentation for **Vexlum Scoring** (`image-scoring-backend`).

## Quick Links

- **[Documentation Index](INDEX.md)** — Full index of all docs, organized by category
- **[Canonical sources](CANONICAL_SOURCES.md)** — API, schema, pipeline vocabulary, cross-repo coordination
- **[Project backlog](../TODO.md)** — Canonical open work; **[00-backlog-workflow](project/00-backlog-workflow.md)** — picking tasks, sync order, counts (aligned with [image-scoring-gallery `docs/project/00-backlog-workflow.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/project/00-backlog-workflow.md))
- **Subfolder indexes** — Each docs subfolder has its own [INDEX.md](INDEX.md) (e.g. [technical/](technical/INDEX.md), [guides/setup/](guides/setup/INDEX.md), [gallery/](gallery/INDEX.md), [planning/](planning/INDEX.md), [features/planned/](features/planned/INDEX.md), [features/implemented/](features/implemented/INDEX.md))
- **[Project README](../README.md)** — Main project overview and quick start
- **[CHANGELOG](../CHANGELOG.md)** — Version history and release notes

## Getting Started

- New to the project? Start with the [Project README](../README.md), then [SCORING_GUIDE.md](guides/getting-started/SCORING_GUIDE.md) or [SIMPLE_CLI_GUIDE.md](guides/getting-started/SIMPLE_CLI_GUIDE.md).
- Creating a gallery? See [GALLERY_CREATION.md](gallery/GALLERY_CREATION.md) or [QUICK_REFERENCE.md](gallery/QUICK_REFERENCE.md).

## Wiki Maintenance

This documentation is an LLM-maintained wiki — see [WIKI_SCHEMA.md](WIKI_SCHEMA.md) for conventions. Prefer **small linked pages** (entities/concepts) over monolithic dumps; example hubs: [PHASE4_KEYWORDS_HUB.md](planning/database/PHASE4_KEYWORDS_HUB.md), [DEBUGGING_SESSIONS_HUB.md](reports/DEBUGGING_SESSIONS_HUB.md).

- **[WIKI_SCHEMA.md](WIKI_SCHEMA.md)** — Page types, naming, linking rules, operations
- **[log.md](log.md)** — Chronological record of all wiki operations
- **Slash commands:** `/wiki-ingest`, `/wiki-query`, `/wiki-lint`

## AI & Agent Helpers

- [AGENTS.md](../AGENTS.md) — MCP server configuration
- [.agent/mcp_tools_reference.md](../.agent/mcp_tools_reference.md) — MCP tools quick reference
- [.agent/workflows/](../.agent/workflows/) — Workflows for run_scoring, verify_system, etc.

## Shipped features (catalog)

- **[features/implemented/INDEX.md](features/implemented/INDEX.md)** — What exists today (API areas, modules, links to deep docs); companion to [features/planned/](features/planned/INDEX.md).

## Infra hubs (quick entry points)

- [.agent/INFRA_QUICKSTART.md](../.agent/INFRA_QUICKSTART.md) — one-page safe commands and pitfalls for agents
- [DEVELOPMENT.md](DEVELOPMENT.md) — venvs, WSL, doctor CLI
- [TESTING.md](TESTING.md) — pytest markers and fast subsets
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — where to look when something fails
- [DIAGNOSTICS.md](DIAGNOSTICS.md) — `scripts/doctor.py`, redacted debug zip, logs
- [DATABASE.md](DATABASE.md) — schema and migrations index
- [ARCHITECTURE.md](ARCHITECTURE.md) — system and pipeline overview index
- [IMAGE_PIPELINE.md](IMAGE_PIPELINE.md) — RAW/NEF, phases, scoring index
- [EXPORT_PIPELINE.md](EXPORT_PIPELINE.md) — API / integration outputs index
- [EMBEDDINGS.md](EMBEDDINGS.md) — link to vector / pgvector docs

## Sibling repository: image-scoring-gallery

Electron desktop app (**[image-scoring-gallery](https://github.com/synthet/image-scoring-gallery)**) shares the API contract and database design with this repo.

| Topic | Documentation (GitHub) |
|--------|-------------------------|
| Docs index | [docs/README.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/README.md) |
| Integration backlog | [docs/integration/TODO.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/integration/TODO.md) |
| DB refactor impact (gallery) | [DATABASE_REFACTOR_ANALYSIS.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/technical/DATABASE_REFACTOR_ANALYSIS.md) |
| Planned embedding UI | [features/planned/embeddings/README.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/planned/embeddings/README.md) |
| Shipped feature catalog (gallery) | [docs/features/implemented/INDEX.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/INDEX.md) |

Cross-project protocol: [AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md).
