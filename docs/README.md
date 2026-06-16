---
type: Documentation Hub
title: Vexlum Scoring Documentation
description: Root documentation hub and recommended reading path for image-scoring-backend.
resource: README.md
tags: [docs, hub, backend, okf]
timestamp: 2026-06-16T00:00:00Z
okf_version: 0.1
---

# Vexlum Scoring Documentation

This is the documentation hub for **image-scoring-backend**, the Python scoring engine and FastAPI/Gradio service behind Vexlum Scoring.

## Quick Links

- [Full documentation index](INDEX.md) - categorized map of the wiki.
- [Canonical sources](CANONICAL_SOURCES.md) - authority map for API, schema, phases, testing, diagnostics, and cross-repo coordination.
- [Project README](../README.md) - product overview and user-facing quick start.
- [Implemented features](features/implemented/INDEX.md) - shipped behavior by area.
- [Planned features](features/planned/INDEX.md) - specs and non-shipped work.
- [Wiki schema](WIKI_SCHEMA.md) - page types, link rules, metadata, and maintenance process.
- [OKF adoption](OKF_ADOPTION.md) - local Open Knowledge Format profile for agent-readable docs.
- [Wiki log](log.md) - append-only record of docs changes.

## Getting Started Path

1. Start with the [Project README](../README.md).
2. Follow the scoring path in [guides/getting-started/SCORING_GUIDE.md](guides/getting-started/SCORING_GUIDE.md) or the simpler CLI path in [guides/getting-started/SIMPLE_CLI_GUIDE.md](guides/getting-started/SIMPLE_CLI_GUIDE.md).
3. Use [ARCHITECTURE.md](ARCHITECTURE.md), [DATABASE.md](DATABASE.md), and [IMAGE_PIPELINE.md](IMAGE_PIPELINE.md) for the system model.
4. Use [TESTING.md](TESTING.md), [DIAGNOSTICS.md](DIAGNOSTICS.md), and [TROUBLESHOOTING.md](TROUBLESHOOTING.md) before changing infrastructure, database, or runner behavior.

## Canonical Sources

Before changing API paths, request/response fields, database columns, phase codes, config keys, or cross-repo integration behavior, read [CANONICAL_SOURCES.md](CANONICAL_SOURCES.md). In short:

- REST API authority: [technical/API_CONTRACT.md](technical/API_CONTRACT.md) and [reference/api/openapi.yaml](reference/api/openapi.yaml).
- Database authority: [technical/DB_SCHEMA.md](technical/DB_SCHEMA.md), [modules/db_postgres.py](../modules/db_postgres.py), and [migrations/versions/](../migrations/versions/).
- Phase terminology authority: [technical/PIPELINE_TERMINOLOGY.md](technical/PIPELINE_TERMINOLOGY.md).
- Cross-repo coordination authority: [technical/AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md).

## Infra And Diagnostics

- [.agent/INFRA_QUICKSTART.md](../.agent/INFRA_QUICKSTART.md) - safe commands, doctor CLI, debug bundles, and known pitfalls for agents.
- [DEVELOPMENT.md](DEVELOPMENT.md) - local environment notes.
- [DIAGNOSTICS.md](DIAGNOSTICS.md) - `scripts/doctor.py`, redacted debug bundle export, logs, and MCP diagnostics.
- [TESTING.md](TESTING.md) - pytest markers and fast local test command.
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) - first triage steps and common failure categories.

## Sibling Gallery

The desktop app lives in **image-scoring-gallery** and consumes backend-owned API, schema, and pipeline terminology.

| Topic | Gallery documentation |
|---|---|
| Docs hub | [image-scoring-gallery docs/README.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/README.md) |
| Canonical source map | [image-scoring-gallery docs/CANONICAL_SOURCES.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/CANONICAL_SOURCES.md) |
| Architecture | [image-scoring-gallery docs/architecture/01-system-overview.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/architecture/01-system-overview.md) |
| Implemented features | [image-scoring-gallery docs/features/implemented/INDEX.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/features/implemented/INDEX.md) |
| Integration backlog | [image-scoring-gallery docs/integration/TODO.md](https://github.com/synthet/image-scoring-gallery/blob/main/docs/integration/TODO.md) |

Cross-project rule: update backend canonical docs first for API, schema, phase, or terminology changes, then update gallery code/docs, and append entries to both `docs/log.md` files.
