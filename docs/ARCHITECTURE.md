# Architecture

This is a hub page. Keep implementation details in the linked pages and update the canonical sources before changing shared contracts.

## Core System

- [architecture/system-overview.md](architecture/system-overview.md) - components, data flow, deployment shape, and runtime entry points.
- [architecture/project-structure.md](architecture/project-structure.md) - repository layout and ownership boundaries.
- [architecture/technical-summary.md](architecture/technical-summary.md) - compact technical summary with diagrams.

## Pipeline

- [architecture/pipeline-architecture.md](architecture/pipeline-architecture.md) - indexing, metadata, scoring, culling, keywords, and run orchestration.
- [technical/PIPELINE_TERMINOLOGY.md](technical/PIPELINE_TERMINOLOGY.md) - canonical phase codes, operation tokens, and user-facing names.
- [technical/PIPELINE_PHASE_RUNNERS.md](technical/PIPELINE_PHASE_RUNNERS.md) - phase runner behavior and sequencing.

## Database And Connectors

- [DATABASE.md](DATABASE.md) - PostgreSQL + pgvector database hub.
- [technical/DB_SCHEMA.md](technical/DB_SCHEMA.md) - schema authority and table map.
- [architecture/DB_CONNECTOR.md](architecture/DB_CONNECTOR.md) - DB connector transport layer and compatibility notes.

## API And Cross-Repo Consumers

- [technical/API_CONTRACT.md](technical/API_CONTRACT.md) - REST contract summary.
- [reference/api/openapi.yaml](reference/api/openapi.yaml) - OpenAPI artifact.
- [technical/AGENT_COORDINATION.md](technical/AGENT_COORDINATION.md) - backend/gallery coordination protocol.
