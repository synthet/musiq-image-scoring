# Documentation

Complete documentation for the Image Scoring project.

## Quick Links

- **[Documentation Index](INDEX.md)** — Full index of all docs, organized by category
- **[Project backlog](../TODO.md)** — Canonical open work; **[00-backlog-workflow](project/00-backlog-workflow.md)** — picking tasks, sync order, counts (aligned with [image-scoring-gallery `docs/project/00-backlog-workflow.md`](https://github.com/synthet/image-scoring-gallery/blob/main/docs/project/00-backlog-workflow.md))
- **Subfolder indexes** — Each docs subfolder has its own [INDEX.md](INDEX.md) (e.g. [technical/](technical/INDEX.md), [setup/](setup/INDEX.md), [gallery/](gallery/INDEX.md), [plans/](plans/INDEX.md))
- **[Project README](../README.md)** — Main project overview and quick start
- **[CHANGELOG](../CHANGELOG.md)** — Version history and release notes

## Getting Started

- New to the project? Start with the [Project README](../README.md), then [SCORING_GUIDE.md](getting-started/SCORING_GUIDE.md) or [SIMPLE_CLI_GUIDE.md](getting-started/SIMPLE_CLI_GUIDE.md).
- Creating a gallery? See [GALLERY_CREATION.md](gallery/GALLERY_CREATION.md) or [QUICK_REFERENCE.md](gallery/QUICK_REFERENCE.md).

## Wiki Maintenance

This documentation is an LLM-maintained wiki — see [WIKI_SCHEMA.md](WIKI_SCHEMA.md) for conventions. Prefer **small linked pages** (entities/concepts) over monolithic dumps; example hubs: [PHASE4_KEYWORDS_HUB.md](plans/database/PHASE4_KEYWORDS_HUB.md), [DEBUGGING_SESSIONS_HUB.md](reports/DEBUGGING_SESSIONS_HUB.md).

- **[WIKI_SCHEMA.md](WIKI_SCHEMA.md)** — Page types, naming, linking rules, operations
- **[log.md](log.md)** — Chronological record of all wiki operations
- **Slash commands:** `/wiki-ingest`, `/wiki-query`, `/wiki-lint`

## AI & Agent Helpers

- [AGENTS.md](../AGENTS.md) — MCP server configuration
- [.agent/mcp_tools_reference.md](../.agent/mcp_tools_reference.md) — MCP tools quick reference
- [.agent/workflows/](../.agent/workflows/) — Workflows for run_scoring, verify_system, etc.

## Sibling repository: image-scoring-gallery

Electron desktop app (**[image-scoring-gallery](https://github.com/synthet/image-scoring-gallery)**) shares the API contract and database design with this repo.

| Topic | Documentation (GitHub) |
|--------|-------------------------|
| Docs index | [docs/README.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/README.md) |
| Integration backlog | [docs/integration/TODO.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/integration/TODO.md) |
| DB refactor impact (gallery) | [DATABASE_REFACTOR_ANALYSIS.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/technical/DATABASE_REFACTOR_ANALYSIS.md) |
| Planned embedding UI | [features/planned/embeddings/README.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/planned/embeddings/README.md) |

Cross-project protocol: [AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md).
